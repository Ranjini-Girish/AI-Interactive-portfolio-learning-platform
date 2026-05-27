#include <cjson/cJSON.h>
#include <dirent.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  char item_id[64];
  char tier[32];
  int demand;
} Item;

static char *read_file(const char *path) {
  FILE *f = fopen(path, "rb");
  if (!f) return NULL;
  if (fseek(f, 0, SEEK_END) != 0) {
    fclose(f);
    return NULL;
  }
  long sz = ftell(f);
  if (sz < 0) {
    fclose(f);
    return NULL;
  }
  rewind(f);
  char *buf = malloc((size_t)sz + 1);
  if (!fread(buf, 1, (size_t)sz, f)) {
    free(buf);
    fclose(f);
    return NULL;
  }
  buf[sz] = '\0';
  fclose(f);
  return buf;
}

static cJSON *load_json(const char *path) {
  char *raw = read_file(path);
  if (!raw) return NULL;
  cJSON *j = cJSON_Parse(raw);
  free(raw);
  return j;
}

static void env_path(const char *key, const char *defv, char *out, size_t n) {
  const char *v = getenv(key);
  snprintf(out, n, "%s", (v && v[0]) ? v : defv);
}

static int tier_rank(const char *tier, cJSON *order) {
  int i = 0;
  cJSON *el;
  cJSON_ArrayForEach(el, order) {
    if (strcmp(el->valuestring, tier) == 0) return i;
    i++;
  }
  return i;
}

static int cmp_items(const void *a, const void *b) {
  const Item *ia = (const Item *)a;
  const Item *ib = (const Item *)b;
  /* rank computed externally via stored sort keys in tier string compare fallback */
  int tr = strcmp(ia->tier, ib->tier);
  if (tr != 0) return tr;
  return strcmp(ia->item_id, ib->item_id);
}

int main(void) {
  char data[256], audit[256];
  env_path("QUOTA_DATA_DIR", "/app/quota_lab", data, sizeof data);
  env_path("QUOTA_AUDIT_DIR", "/app/audit", audit, sizeof audit);

  char path[512];
  snprintf(path, sizeof path, "%s/policy.json", data);
  cJSON *policy = load_json(path);
  snprintf(path, sizeof path, "%s/events.json", data);
  cJSON *events = load_json(path);
  if (!policy || !events) return 1;

  int day = cJSON_GetObjectItem(policy, "audit_day")->valueint;
  cJSON *order = cJSON_GetObjectItem(policy, "tier_order");
  cJSON *tier_caps = cJSON_GetObjectItem(policy, "tier_caps");

  typedef struct {
    char tier[32];
    int cap;
    int rem;
  } TierCap;
  TierCap tiers[32];
  int nt = 0;
  cJSON *cap_el;
  cJSON_ArrayForEach(cap_el, tier_caps) {
    snprintf(tiers[nt].tier, sizeof tiers[nt].tier, "%s", cap_el->string);
    tiers[nt].cap = cap_el->valueint;
    tiers[nt].rem = cap_el->valueint;
    nt++;
  }

  for (int i = 0; i < nt; i++) tiers[i].rem = tiers[i].cap;

  cJSON *derates = cJSON_GetObjectItem(events, "tier_derates");
  if (derates && cJSON_IsArray(derates)) {
    cJSON *d;
    cJSON_ArrayForEach(d, derates) {
      int s = cJSON_GetObjectItem(d, "start_day")->valueint;
      int e = cJSON_GetObjectItem(d, "end_day")->valueint;
      if (s <= day && day <= e) {
        const char *t = cJSON_GetObjectItem(d, "tier")->valuestring;
        int bp = cJSON_GetObjectItem(d, "factor_bp")->valueint;
        for (int i = 0; i < nt; i++) {
          if (strcmp(tiers[i].tier, t) == 0) {
            tiers[i].cap = tiers[i].cap * bp / 10000;
            tiers[i].rem = tiers[i].cap;
          }
        }
      }
    }
  }

  char frozen_ids[64][64];
  int nf = 0;
  cJSON *freezes = cJSON_GetObjectItem(events, "item_freezes");
  if (freezes && cJSON_IsArray(freezes)) {
    cJSON *f;
    cJSON_ArrayForEach(f, freezes) {
      int s = cJSON_GetObjectItem(f, "start_day")->valueint;
      int e = cJSON_GetObjectItem(f, "end_day")->valueint;
      if (s <= day && day <= e) {
        snprintf(frozen_ids[nf++], sizeof frozen_ids[0], "%s",
                 cJSON_GetObjectItem(f, "item_id")->valuestring);
      }
    }
  }

  Item items[128];
  int ni = 0;
  snprintf(path, sizeof path, "%s/items", data);
  DIR *dir = opendir(path);
  if (!dir) return 1;
  struct dirent *ent;
  while ((ent = readdir(dir)) != NULL && ni < 128) {
    size_t len = strlen(ent->d_name);
    if (len < 6 || strcmp(ent->d_name + len - 5, ".json") != 0) continue;
    snprintf(path, sizeof path, "%s/items/%s", data, ent->d_name);
    cJSON *it = load_json(path);
    if (!it) continue;
    snprintf(items[ni].item_id, sizeof items[ni].item_id, "%s",
             cJSON_GetObjectItem(it, "item_id")->valuestring);
    snprintf(items[ni].tier, sizeof items[ni].tier, "%s",
             cJSON_GetObjectItem(it, "tier")->valuestring);
    items[ni].demand = cJSON_GetObjectItem(it, "demand")->valueint;
    cJSON_Delete(it);
    ni++;
  }
  closedir(dir);

  for (int i = 0; i < ni - 1; i++) {
    for (int j = i + 1; j < ni; j++) {
      int ri = tier_rank(items[i].tier, order);
      int rj = tier_rank(items[j].tier, order);
      int swap = 0;
      if (ri != rj) swap = ri > rj;
      else if (strcmp(items[i].tier, items[j].tier) != 0)
        swap = strcmp(items[i].tier, items[j].tier) > 0;
      else
        swap = strcmp(items[i].item_id, items[j].item_id) > 0;
      if (swap) {
        Item tmp = items[i];
        items[i] = items[j];
        items[j] = tmp;
      }
    }
  }

  int sc_frozen = 0, sc_ok = 0, sc_short = 0;
  cJSON *rows = cJSON_CreateArray();
  for (int i = 0; i < ni; i++) {
    int is_frozen = 0;
    for (int f = 0; f < nf; f++) {
      if (strcmp(frozen_ids[f], items[i].item_id) == 0) {
        is_frozen = 1;
        break;
      }
    }
    int left = 0;
    for (int t = 0; t < nt; t++) {
      if (strcmp(tiers[t].tier, items[i].tier) == 0) left = tiers[t].rem;
    }
    int alloc = 0;
    const char *status;
    if (is_frozen) {
      status = "frozen";
      sc_frozen++;
    } else {
      alloc = items[i].demand < left ? items[i].demand : left;
      for (int t = 0; t < nt; t++) {
        if (strcmp(tiers[t].tier, items[i].tier) == 0) tiers[t].rem = left - alloc;
      }
      status = (alloc == items[i].demand) ? "ok" : "shortfall";
      if (alloc == items[i].demand) sc_ok++;
      else sc_short++;
    }
    cJSON *row = cJSON_CreateObject();
    cJSON_AddStringToObject(row, "item_id", items[i].item_id);
    cJSON_AddStringToObject(row, "tier", items[i].tier);
    cJSON_AddStringToObject(row, "status", status);
    cJSON_AddNumberToObject(row, "demand", items[i].demand);
    cJSON_AddNumberToObject(row, "allocated", is_frozen ? 0 : alloc);
    cJSON_AddItemToArray(rows, row);
  }

  char touched[32][32];
  int ntouch = 0;
  cJSON *el;
  cJSON_ArrayForEach(el, rows) {
    if (cJSON_GetObjectItem(el, "allocated")->valueint > 0) {
      const char *t = cJSON_GetObjectItem(el, "tier")->valuestring;
      int seen = 0;
      for (int k = 0; k < ntouch; k++) {
        if (strcmp(touched[k], t) == 0) {
          seen = 1;
          break;
        }
      }
      if (!seen) snprintf(touched[ntouch++], sizeof touched[0], "%s", t);
    }
  }
  for (int i = 0; i < ntouch - 1; i++) {
    for (int j = i + 1; j < ntouch; j++) {
      if (strcmp(touched[i], touched[j]) > 0) {
        char tmp[32];
        snprintf(tmp, sizeof tmp, "%s", touched[i]);
        snprintf(touched[i], sizeof touched[i], "%s", touched[j]);
        snprintf(touched[j], sizeof touched[j], "%s", tmp);
      }
    }
  }

  cJSON *touched_arr = cJSON_CreateArray();
  for (int i = 0; i < ntouch; i++) cJSON_AddItemToArray(touched_arr, cJSON_CreateString(touched[i]));

  cJSON *status_counts = cJSON_CreateObject();
  cJSON_AddNumberToObject(status_counts, "frozen", sc_frozen);
  cJSON_AddNumberToObject(status_counts, "ok", sc_ok);
  cJSON_AddNumberToObject(status_counts, "shortfall", sc_short);

  cJSON *summary = cJSON_CreateObject();
  cJSON_AddNumberToObject(summary, "audit_day", day);
  cJSON_AddNumberToObject(summary, "items_processed", ni);
  cJSON_AddNumberToObject(summary, "frozen_items", sc_frozen);
  cJSON_AddItemToObject(summary, "status_counts", status_counts);
  cJSON_AddItemToObject(summary, "tiers_touched", touched_arr);

  cJSON *alloc_root = cJSON_CreateObject();
  cJSON_AddItemToObject(alloc_root, "items", rows);

  snprintf(path, sizeof path, "%s/allocations.json", audit);
  char *out1 = cJSON_Print(alloc_root);
  FILE *f1 = fopen(path, "w");
  fprintf(f1, "%s\n", out1);
  fclose(f1);
  free(out1);

  snprintf(path, sizeof path, "%s/summary.json", audit);
  char *out2 = cJSON_Print(summary);
  FILE *f2 = fopen(path, "w");
  fprintf(f2, "%s\n", out2);
  fclose(f2);
  free(out2);

  cJSON_Delete(policy);
  cJSON_Delete(events);
  cJSON_Delete(alloc_root);
  cJSON_Delete(summary);
  return 0;
}
