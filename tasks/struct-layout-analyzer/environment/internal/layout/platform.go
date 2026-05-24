package layout

// Platform defines the target platform configuration
// for memory layout computation.
type Platform struct {
	Name        string
	PointerSize int
	MaxAlign    int
}

// AMD64 is the linux/amd64 platform configuration.
var AMD64 = Platform{
	Name:        "linux_amd64",
	PointerSize: 8,
	MaxAlign:    8,
}
