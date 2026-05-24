package types

type FieldLayout struct {
	Name         string
	TypeName     string
	Offset       int
	Size         int
	Alignment    int
	PaddingAfter int
}
