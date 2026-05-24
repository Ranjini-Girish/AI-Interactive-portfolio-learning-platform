package types

type StructLayout struct {
	Name         string
	Size         int
	Alignment    int
	Fields       []FieldLayout
	TotalPadding int
	IsOptimal    bool
	OptimalSize  int
	OptimalOrder []string
}
