package profile

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

type sharedCase struct {
	Name      string `json:"name"`
	Steps     []Step `json:"steps"`
	MinLength *int   `json:"min_length"`
	MaxLength *int   `json:"max_length"`
	Sample    string `json:"sample"`
	Expected  string `json:"expected"`
	Error     bool   `json:"error"`
}

func TestSharedNormalizationCases(t *testing.T) {
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("no se pudo ubicar el archivo de prueba")
	}
	path := filepath.Join(filepath.Dir(file), "..", "..", "..", "docs", "reader-profiles", "normalization-cases.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("leer casos: %v", err)
	}
	var cases []sharedCase
	if err := json.Unmarshal(raw, &cases); err != nil {
		t.Fatalf("json: %v", err)
	}
	if len(cases) == 0 {
		t.Fatal("no hay casos compartidos")
	}
	for _, item := range cases {
		t.Run(item.Name, func(t *testing.T) {
			minLength, maxLength := 0, 0
			if item.MinLength != nil {
				minLength = *item.MinLength
			}
			if item.MaxLength != nil {
				maxLength = *item.MaxLength
			}
			got, err := Apply(item.Sample, item.Steps, minLength, maxLength)
			if item.Error {
				if err == nil {
					t.Fatalf("se esperaba error, resultado %q", got)
				}
				return
			}
			if err != nil {
				t.Fatalf("apply: %v", err)
			}
			if got != item.Expected {
				t.Fatalf("resultado = %q, esperaba %q", got, item.Expected)
			}
		})
	}
}

func TestUnknownOperation(t *testing.T) {
	_, err := Apply("ab", []Step{{Op: "invert"}}, 0, 0)
	if err == nil {
		t.Fatal("se esperaba error")
	}
}
