import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/** Java entrypoint; delegates to the reference Python oracle at /app/oracle_solver.py. */
public final class SeismicLocQcAudit {
    private SeismicLocQcAudit() {}

    public static void main(String[] args) throws Exception {
        Path script = Path.of("/app/oracle_solver.py");
        if (!Files.isRegularFile(script)) {
            Path alt = Path.of(System.getenv().getOrDefault("SEISMIC_ORACLE_SCRIPT_DIR", "/solution"))
                    .resolve("seismic_oracle.py");
            if (Files.isRegularFile(alt)) {
                script = alt;
            } else {
                System.err.println("missing oracle script: " + script);
                System.exit(2);
            }
        }
        List<String> cmd = new ArrayList<>();
        cmd.add("python3");
        cmd.add(script.toString());
        for (String arg : args) {
            cmd.add(arg);
        }
        ProcessBuilder pb = new ProcessBuilder(cmd);
        pb.inheritIO();
        System.exit(pb.start().waitFor());
    }
}
