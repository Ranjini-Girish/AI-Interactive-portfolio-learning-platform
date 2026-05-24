package main

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
)

func main() {
	appRoot := "/app"
	if len(os.Args) > 1 {
		appRoot = os.Args[1]
	}

	outDir := filepath.Join(appRoot, "output")
	os.MkdirAll(outDir, 0755)

	stub := map[string]interface{}{
		"schema_version":  1,
		"summary":         map[string]interface{}{},
		"source_sha256":   map[string]interface{}{},
		"query_results":   []interface{}{},
		"findings":        []interface{}{},
	}

	data, _ := json.MarshalIndent(stub, "", "  ")
	outPath := filepath.Join(outDir, "dependency_audit.json")
	os.WriteFile(outPath, append(data, '\n'), 0644)
	fmt.Println("wrote", outPath)
}
