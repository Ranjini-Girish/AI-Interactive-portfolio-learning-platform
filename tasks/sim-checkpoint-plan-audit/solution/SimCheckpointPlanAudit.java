import java.nio.file.Files;
import java.nio.file.Path;

/** Runs the reference Python oracle shipped beside this class. */
public final class SimCheckpointPlanAudit {
    private SimCheckpointPlanAudit() {}

    public static void main(String[] args) throws Exception {
        Path scriptDir =
                Path.of(System.getenv().getOrDefault("SIM_ORACLE_SCRIPT_DIR", "/solution"));
        Path script = scriptDir.resolve("sim_oracle.py");
        if (!Files.isRegularFile(script)) {
            System.err.println("missing oracle script: " + script);
            System.exit(2);
        }
        var cmd = new java.util.ArrayList<String>();
        cmd.add("python3");
        cmd.add(script.toString());

        var pb = new ProcessBuilder(cmd);
        pb.inheritIO();
        int rc = pb.start().waitFor();
        System.exit(rc);
    }
}
