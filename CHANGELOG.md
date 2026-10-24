# Changelog

## 2.3.0
- Added built-in circuit examples: Bell, H superposition, X and 3-qubit GHZ.
- Added four known-answer statevector diagnostics and a report endpoint.
- Updated API and package version to 2.3.0.

## 2.2.0
- Added undo/redo history for circuit edits.
- Added gate duplication and circuit connection validation UI.
- Updated API and package version to 2.2.0.

## 2.1.0
- Added gate operation list with drag-and-drop reordering.
- Added move-up, move-down, and remove controls for gates.
- Updated API and package version to 2.1.0.

## 2.0.0
- Added quick gate palette for common one- and two-qubit gates.
- Added preflight circuit validation API and UI warnings.
- Updated API and package version to 2.0.0.

## 1.9.0
- Live SVG circuit diagram generated from the current gate list.
- Probability bar chart for ideal basis-state probabilities.
- Fixed rotation-angle handling in sampled execution; OpenQASM export retains configured angles.

## 1.8.0
- Visual gate builder with rotation-angle support.
- Statevector inspector for ideal amplitudes and basis probabilities.
- Added statevector and gate-catalog API endpoints.
- Retained job queue, circuit JSON files and experiment history.


## 2.4.0
- Dodano eksport raportu diagnostycznego w formacie JSON ze znacznikiem czasu.
- Dodano eksport pojedynczego eksperymentu: metadane, obwód i wyniki pomiarów.
- Dodano przyciski eksportu w interfejsie webowym.
- Rozszerzono testy API o ścieżki eksportu.


## 2.5.0
- Dodano import wyeksportowanych eksperymentów JSON.
- Dodano ponowne uruchamianie zapisanych obwodów z historii eksperymentów.
- Rozszerzono UI o import pliku i przycisk ponownego uruchomienia.
- Dodano testy API dla nieobsługiwanego formatu importu i brakującego eksperymentu.


## 2.6.0
- Dodano automatyczny lokalny zapis i przywracanie sesji edytora.
- Dodano raport porównawczy dla wielu eksperymentów.
- Dodano eksport porównania dwóch eksperymentów do CSV.
- Dodano testy API dla walidacji parametrów porównania.


## 2.7.0
- Dodano endpoint ewolucji wektora stanu po każdej bramce.
- Dodano interaktywny panel wykresów prawdopodobieństwa dla kolejnych etapów.
- Dodano podgląd amplitud zespolonych.
- Rozszerzono testy API o endpoint ewolucji.


## 2.8.0
- Dodano porównanie idealnej i zaszumionej ewolucji obwodu.
- Dodano metrykę total variation distance (TVD) dla każdego etapu.
- Dodano wykresy porównawcze oraz eksport raportu JSON.
- Dodano test limitu długości raportu szumu.


## 2.9.0
- Added repeated finite-shot stability analysis against ideal statevector probabilities.
- Added mean and standard deviation of total variation distance (TVD).
- Added UI report table and JSON export.
- Added endpoint validation and API tests.
