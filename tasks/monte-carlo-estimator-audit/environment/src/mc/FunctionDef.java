package mc;

/**
 * Represents a mathematical function loaded from a JSON definition file.
 * Supports evaluation at arbitrary points within the function's domain.
 *
 * Supported types: polynomial, trigonometric, exponential, logarithmic,
 * rational, absolute_value, gaussian_density, step, oscillatory, constant.
 */
public class FunctionDef {
    private String id;
    private String type;
    private double exactIntegral;
    private double domainLow;
    private double domainHigh;

    // TODO: implement function loading and evaluation
}
