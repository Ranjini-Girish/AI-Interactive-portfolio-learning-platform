package types

type Report struct {
	Platform    string         `json:"platform"`
	PointerSize int            `json:"pointer_size"`
	Structs     []StructLayout `json:"structs"`
}
