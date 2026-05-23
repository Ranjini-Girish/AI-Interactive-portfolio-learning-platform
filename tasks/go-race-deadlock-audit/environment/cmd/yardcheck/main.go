package main

import (
	"flag"
	"fmt"
	"os"

	"yardops.local/yardcheck/internal/audit"
)

func main() {
	manifestPath := flag.String("manifest", "/app/data/manifest.csv", "manifest CSV path")
	appointmentsPath := flag.String("appointments", "/app/data/appointments.csv", "appointments CSV path")
	eventsPath := flag.String("events", "/app/data/events.ndjson", "events ndjson path")
	outPath := flag.String("out", "/app/out/yard_report.json", "output report path")
	flag.Parse()

	if err := audit.WriteReport(*manifestPath, *appointmentsPath, *eventsPath, *outPath); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
