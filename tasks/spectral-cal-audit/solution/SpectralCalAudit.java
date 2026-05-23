/**
 * Spectral calibration verifier contract requires a C++17 {@code /app/build/calibrate} binary.
 * The reference oracle is deployed by {@code solve.sh} via {@code solve_accepted.sh}.
 */
public final class SpectralCalAudit {
    private SpectralCalAudit() {}

    public static void main(String[] args) {
        System.err.println("Use solve.sh (C++ calibrate binary), not SpectralCalAudit.java");
        System.exit(1);
    }
}
