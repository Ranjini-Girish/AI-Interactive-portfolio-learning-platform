import com.google.gson.Gson
import com.google.gson.GsonBuilder
import java.nio.charset.StandardCharsets
import java.nio.file.Files
import java.nio.file.Path
import java.nio.file.Paths
import kotlin.math.min

data class ItemRow(
    val item_id: String,
    val tier: String,
    val status: String,
    val demand: Int,
    val allocated: Int,
)

fun main() {
    val data = Paths.get(System.getenv().getOrDefault("QUOTA_DATA_DIR", "/app/quota_lab"))
    val audit = Paths.get(System.getenv().getOrDefault("QUOTA_AUDIT_DIR", "/app/audit"))
    Files.createDirectories(audit)
    val gson = Gson()
    val pretty = GsonBuilder().setPrettyPrinting().create()

    @Suppress("UNCHECKED_CAST")
    fun readMap(p: Path): Map<String, Any> = gson.fromJson(Files.readString(p, StandardCharsets.UTF_8), Map::class.java) as Map<String, Any>

    val policy = readMap(data.resolve("policy.json"))
    val events = readMap(data.resolve("events.json"))
    val day = (policy["audit_day"] as Number).toInt()
    @Suppress("UNCHECKED_CAST")
    val order = policy["tier_order"] as List<String>
    @Suppress("UNCHECKED_CAST")
    val capsNum = policy["tier_caps"] as Map<String, Number>
    val caps = capsNum.mapValues { it.value.toInt() }.toMutableMap()

    @Suppress("UNCHECKED_CAST")
    val derates = events["tier_derates"] as? List<Map<String, Any>> ?: emptyList()
    for (d in derates) {
        val s = (d["start_day"] as Number).toInt()
        val e = (d["end_day"] as Number).toInt()
        if (s <= day && day <= e) {
            val t = d["tier"] as String
            if (t in caps) caps[t] = caps[t]!! * (d["factor_bp"] as Number).toInt() / 10000
        }
    }

    @Suppress("UNCHECKED_CAST")
    val freezes = events["item_freezes"] as? List<Map<String, Any>> ?: emptyList()
    val frozen = freezes.filter {
        val s = (it["start_day"] as Number).toInt()
        val e = (it["end_day"] as Number).toInt()
        s <= day && day <= e
    }.map { it["item_id"] as String }.toSet()

    fun tierRank(tier: String): Int = order.indexOf(tier).let { if (it >= 0) it else order.size }

    val itemPaths = Files.list(data.resolve("items"))
        .filter { it.toString().endsWith(".json") }
        .sorted()
        .toList()
    val items = itemPaths
        .map { readMap(it) }
        .sortedWith(compareBy({ tierRank(it["tier"] as String) }, { it["tier"] as String }, { it["item_id"] as String }))

    val tierRem = caps.toMutableMap()
    val rows = mutableListOf<ItemRow>()
    val sc = mutableMapOf("frozen" to 0, "ok" to 0, "shortfall" to 0)

    for (it in items) {
        val iid = it["item_id"] as String
        val tier = it["tier"] as String
        val demand = (it["demand"] as Number).toInt()
        if (iid in frozen) {
            rows.add(ItemRow(iid, tier, "frozen", demand, 0))
            sc["frozen"] = sc["frozen"]!! + 1
            continue
        }
        val left = tierRem.getOrDefault(tier, 0)
        val alloc = min(demand, left)
        tierRem[tier] = left - alloc
        val st = if (alloc == demand) "ok" else "shortfall"
        sc[st] = sc[st]!! + 1
        rows.add(ItemRow(iid, tier, st, demand, alloc))
    }

    val touched = rows.filter { it.allocated > 0 }.map { it.tier }.distinct().sorted()
    val summary = linkedMapOf(
        "audit_day" to day,
        "items_processed" to items.size,
        "frozen_items" to sc["frozen"],
        "status_counts" to sc,
        "tiers_touched" to touched,
    )

    fun write(name: String, obj: Any) {
        Files.writeString(audit.resolve(name), pretty.toJson(obj) + "\n", StandardCharsets.UTF_8)
    }
    write("allocations.json", mapOf("items" to rows))
    write("summary.json", summary)
}
