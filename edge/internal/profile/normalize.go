// Package profile aplica los pasos de un ReaderProfile.
// La semántica es la misma que apps/access/normalization.py.
package profile

import (
	"fmt"
	"math/big"
	"regexp"
	"strings"
	"sync"
	"unicode/utf8"
)

// Step es un paso de normalización tal como viaja en el delta.
type Step struct {
	Op      string `json:"op"`
	Pattern string `json:"pattern,omitempty"`
	Length  int    `json:"length,omitempty"`
	Char    string `json:"char,omitempty"`
}

// Error describe un fallo de normalización que el motor convierte en MALFORMED_READ.
type Error struct {
	Msg string
}

func (e *Error) Error() string {
	return e.Msg
}

var (
	hexPattern = regexp.MustCompile(`^[0-9A-Fa-f]+$`)
	decPattern = regexp.MustCompile(`^[0-9]+$`)
	compiled   sync.Map
)

// Apply ejecuta los pasos en orden y luego comprueba la longitud.
// minLength o maxLength en cero no imponen límite.
func Apply(value string, steps []Step, minLength, maxLength int) (string, error) {
	current := value
	for index, step := range steps {
		next, err := applyStep(current, step)
		if err != nil {
			return "", fmt.Errorf("paso %d (%s): %w", index+1, step.Op, err)
		}
		current = next
	}
	length := utf8.RuneCountInString(current)
	if minLength > 0 && length < minLength {
		return "", &Error{Msg: fmt.Sprintf("longitud %d menor que el mínimo %d", length, minLength)}
	}
	if maxLength > 0 && length > maxLength {
		return "", &Error{Msg: fmt.Sprintf("longitud %d mayor que el máximo %d", length, maxLength)}
	}
	return current, nil
}

func applyStep(value string, step Step) (string, error) {
	switch step.Op {
	case "trim":
		return strings.TrimSpace(value), nil
	case "upper":
		return strings.ToUpper(value), nil
	case "strip_leading_zeros":
		stripped := strings.TrimLeft(value, "0")
		if stripped == "" {
			return "0", nil
		}
		return stripped, nil
	case "regex_extract":
		return regexExtract(value, step.Pattern)
	case "hex_to_dec":
		if !hexPattern.MatchString(value) {
			return "", &Error{Msg: "el valor no es hexadecimal"}
		}
		number := new(big.Int)
		if _, ok := number.SetString(value, 16); !ok {
			return "", &Error{Msg: "el valor no es hexadecimal"}
		}
		return number.String(), nil
	case "dec_to_hex":
		if !decPattern.MatchString(value) {
			return "", &Error{Msg: "el valor no es decimal"}
		}
		number := new(big.Int)
		if _, ok := number.SetString(value, 10); !ok {
			return "", &Error{Msg: "el valor no es decimal"}
		}
		return strings.ToUpper(number.Text(16)), nil
	case "pad_left":
		return padLeft(value, step)
	default:
		return "", &Error{Msg: "operación desconocida: " + step.Op}
	}
}

func regexExtract(value, pattern string) (string, error) {
	if pattern == "" {
		return "", &Error{Msg: "el paso requiere pattern"}
	}
	expression, err := compile(pattern)
	if err != nil {
		return "", &Error{Msg: "expresión regular inválida"}
	}
	index := expression.FindStringSubmatchIndex(value)
	if index == nil {
		return "", &Error{Msg: "la expresión regular no encontró coincidencias"}
	}
	if expression.NumSubexp() >= 1 {
		if index[2] < 0 {
			return "", &Error{Msg: "la expresión regular no encontró coincidencias"}
		}
		return value[index[2]:index[3]], nil
	}
	return value[index[0]:index[1]], nil
}

func compile(pattern string) (*regexp.Regexp, error) {
	if cached, ok := compiled.Load(pattern); ok {
		if expression, valid := cached.(*regexp.Regexp); valid {
			return expression, nil
		}
	}
	expression, err := regexp.Compile(pattern)
	if err != nil {
		return nil, err
	}
	compiled.Store(pattern, expression)
	return expression, nil
}

func padLeft(value string, step Step) (string, error) {
	if step.Length < 1 {
		return "", &Error{Msg: "el paso requiere length entero positivo"}
	}
	char := step.Char
	if char == "" {
		char = "0"
	}
	if utf8.RuneCountInString(char) != 1 {
		return "", &Error{Msg: "el paso requiere un único carácter de relleno"}
	}
	missing := step.Length - utf8.RuneCountInString(value)
	if missing <= 0 {
		return value, nil
	}
	return strings.Repeat(char, missing) + value, nil
}
