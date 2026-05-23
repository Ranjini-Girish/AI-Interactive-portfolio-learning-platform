package audit

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

type ManifestRow struct {
	ContainerID string
	Booking     string
}

type Appointment struct {
	Booking  string
	Start    time.Time
	End      time.Time
	Capacity int
}

type Event struct {
	ContainerID string
	Type        string
	Timestamp   time.Time
}

type eventRecord struct {
	ContainerID string `json:"container_id"`
	Type        string `json:"type"`
	Timestamp   string `json:"timestamp"`
}

type ContainerReport struct {
	ContainerID          string   `json:"container_id"`
	Booking              string   `json:"booking"`
	Status               string   `json:"status"`
	ReasonCodes          []string `json:"reason_codes"`
	AppointmentWindowUTC []string `json:"appointment_window_utc"`
	LastEventType        string   `json:"last_event_type"`
	LastEventUTC         string   `json:"last_event_utc"`
}

type Report struct {
	GeneratedAt string            `json:"generated_at"`
	Summary     map[string]int    `json:"summary"`
	Containers  []ContainerReport `json:"containers"`
}

func WriteReport(manifestPath, appointmentsPath, eventsPath, outPath string) error {
	manifest, err := LoadManifest(manifestPath)
	if err != nil {
		return err
	}
	appointments, err := LoadAppointments(appointmentsPath)
	if err != nil {
		return err
	}
	events, err := LoadEvents(eventsPath)
	if err != nil {
		return err
	}
	report := BuildReport(manifest, appointments, events)
	data, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	return os.WriteFile(outPath, append(data, '\n'), 0o644)
}

func LoadManifest(path string) ([]ManifestRow, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	reader.TrimLeadingSpace = true
	records, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	var rows []ManifestRow
	for i, rec := range records {
		if i == 0 {
			continue
		}
		if len(rec) < 2 {
			return nil, fmt.Errorf("manifest row %d has too few columns", i+1)
		}
		rows = append(rows, ManifestRow{ContainerID: rec[0], Booking: rec[1]})
	}
	return rows, nil
}

func LoadAppointments(path string) (map[string]Appointment, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	reader.TrimLeadingSpace = true
	records, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	appointments := map[string]Appointment{}
	for i, rec := range records {
		if i == 0 {
			continue
		}
		if len(rec) < 5 {
			return nil, fmt.Errorf("appointment row %d has too few columns", i+1)
		}
		start, err := time.Parse("2006-01-02 15:04", rec[1])
		if err != nil {
			return nil, err
		}
		end, err := time.Parse("2006-01-02 15:04", rec[2])
		if err != nil {
			return nil, err
		}
		capacity, err := strconv.Atoi(rec[4])
		if err != nil {
			return nil, err
		}
		appointments[rec[0]] = Appointment{Booking: rec[0], Start: start, End: end, Capacity: capacity}
	}
	return appointments, nil
}

func LoadEvents(path string) ([]Event, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var events []Event
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		if scanner.Text() == "" {
			continue
		}
		var rec eventRecord
		if err := json.Unmarshal(scanner.Bytes(), &rec); err != nil {
			return nil, err
		}
		ts, err := time.Parse(time.RFC3339, rec.Timestamp)
		if err != nil {
			return nil, err
		}
		events = append(events, Event{ContainerID: rec.ContainerID, Type: rec.Type, Timestamp: ts})
	}
	return events, scanner.Err()
}

func BuildReport(manifest []ManifestRow, appointments map[string]Appointment, events []Event) Report {
	lastEvent := map[string]Event{}
	lastGateIn := map[string]Event{}
	held := map[string]bool{}
	var generated time.Time

	for _, event := range events {
		lastEvent[event.ContainerID] = event
		if event.Type == "gate_in" {
			lastGateIn[event.ContainerID] = event
		}
		if event.Type == "hold" {
			held[event.ContainerID] = true
		}
		if event.Type == "release" {
			held[event.ContainerID] = false
		}
		if event.Timestamp.After(generated) {
			generated = event.Timestamp
		}
	}

	summary := map[string]int{
		"ready":               0,
		"blocked":             0,
		"stale":               0,
		"overbooked":          0,
		"unknown_appointment": 0,
	}
	var containers []ContainerReport
	for _, row := range manifest {
		status := "ready"
		reasons := []string{}
		window := []string{}
		appointment, ok := appointments[row.Booking]
		if ok {
			window = []string{appointment.Start.UTC().Format(time.RFC3339), appointment.End.UTC().Format(time.RFC3339)}
		}
		if !ok {
			status = "unknown_appointment"
			reasons = append(reasons, "NO_APPOINTMENT")
		} else if held[row.ContainerID] {
			status = "blocked"
			reasons = append(reasons, "ACTIVE_HOLD")
		} else if gate, ok := lastGateIn[row.ContainerID]; !ok {
			status = "stale"
			reasons = append(reasons, "NO_GATE_IN")
		} else if gate.Timestamp.Before(appointment.Start) || !gate.Timestamp.Before(appointment.End) {
			status = "stale"
			reasons = append(reasons, "OUTSIDE_WINDOW")
		}
		summary[status]++

		var lastType, lastUTC string
		if event, ok := lastEvent[row.ContainerID]; ok {
			lastType = event.Type
			lastUTC = event.Timestamp.UTC().Format(time.RFC3339)
		}
		containers = append(containers, ContainerReport{
			ContainerID:          row.ContainerID,
			Booking:              row.Booking,
			Status:               status,
			ReasonCodes:          reasons,
			AppointmentWindowUTC: window,
			LastEventType:        lastType,
			LastEventUTC:         lastUTC,
		})
	}

	var generatedAt string
	if !generated.IsZero() {
		generatedAt = generated.UTC().Format(time.RFC3339)
	}
	return Report{GeneratedAt: generatedAt, Summary: summary, Containers: containers}
}
