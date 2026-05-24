package types

type NodeID uint32

type Score float64

type PacketHeader struct {
	Active    bool
	SeqNum    int64
	Priority  uint16
	Timestamp int64
}

type EventMarker struct {
	Timestamp int64
	Category  uint32
	Flags     uint32
	_         struct{}
}

type Measurement struct {
	ID     uint32
	Sample complex64
	Scale  float64
}

type AlignmentTrap struct {
	A byte
	_ [0]int64
	B byte
}

type NetworkPacket struct {
	Version  uint8
	Src      uint64
	TTL      uint8
	Dst      uint64
	Checksum uint32
	Length   uint16
}

type Handler struct {
	Name      string
	Callback  func(int) error
	Processor interface{}
	Priority  int32
	Enabled   bool
}

type Edge struct {
	From   NodeID
	To     NodeID
	Weight Score
}

type Graph struct {
	ID       int64
	Edges    []Edge
	Metadata map[string]interface{}
	Directed bool
}
