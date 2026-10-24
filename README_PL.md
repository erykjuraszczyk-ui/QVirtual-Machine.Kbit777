# Qwantum VM Windows 2.9

Lokalny symulator obwodów kwantowych z Qiskit Aer, edytorem bramek i analizą idealnego wektora stanu.

> To symulator programowy, nie fizyczny procesor kwantowy. Limit: 8 kubitów na obwód. 777 węzłów Nebiru to wizualizacja koncepcyjna.

## Uruchomienie
1. Windows 10/11 64-bit i Python 3.12 64-bit.
2. Rozpakuj ZIP, np. do `C:\QwantumVM23`.
3. Uruchom `install_windows.bat`.
4. Uruchom `run_windows.bat`.
5. Otwórz `http://127.0.0.1:8000`.
6. Dodaj bramki i kliknij „Oblicz stan kwantowy” lub „Dodaj do kolejki”.

Testy: `run_tests_windows.bat`.

## Nowości 2.3
- Biblioteka przykładów: stan Bella, superpozycja H, test X i stan GHZ (3 kubity).
- Automatyczna diagnostyka czterech znanych przypadków z raportem wyników.
- Endpoint `GET /api/diagnostics`.
- Cofanie i ponawianie zmian (Undo/Redo).
- Duplikowanie bramek i edycja kolejności przez przeciąganie lub przyciski ↑/↓.
- Kontrola połączeń kubitów i parametrów obwodu.
- Paleta szybkiego dodawania bramek H, X, Y, Z, S, T, RX, RY, RZ, CX, CZ i SWAP.
- Walidacja obwodu przed uruchomieniem, wraz z ostrzeżeniami.
- Schemat obwodu generowany na żywo oraz wykres prawdopodobieństw stanów bazowych.
- Kąty `rx`, `ry`, `rz` są teraz respektowane przez symulację i eksport OpenQASM.
- Amplitudy zespolone oraz prawdopodobieństwa stanów bazowych.
- `POST /api/statevector` i `GET /api/circuit/gates`; API wersja `2.3.0`; endpoint `POST /api/circuit/validate`.
- Zachowana kolejka workerów, historia, porównywanie wyników i pliki JSON.

## Uwagi
- Wektor stanu jest idealny i nie uwzględnia szumu ani losowości pomiarów.
- Maksymalnie 8 kubitów.
- Serwer nasłuchuje na `127.0.0.1`; nie wystawiaj go bezpośrednio do Internetu.


## Nowości w wersji 2.4
- Eksport raportu diagnostycznego do pliku JSON przez przycisk w panelu diagnostyki lub endpoint `GET /api/diagnostics/export`.
- Eksport zapisanego eksperymentu wraz z rozkładem wyników i definicją obwodu przez przycisk w historii lub endpoint `GET /api/experiments/{id}/export`.
- Pliki eksportu zawierają identyfikator formatu i jego wersję, co ułatwia późniejsze importowanie w kolejnych wydaniach.
- Wersja API: `2.4.0`.

Eksport diagnostyki uruchamia testy ponownie i zapisuje świeży raport. Wyniki eksperymentów pochodzą z symulatora Qiskit Aer, jeśli jest poprawnie zainstalowany.


## Nowości w wersji 2.5
- Import eksperymentu z pliku JSON wyeksportowanego przez Qwantum VM (`qwantum-experiment`).
- Ponowne uruchomienie zapisanego eksperymentu z konfiguracji obwodu i dodanie go do kolejki obliczeń.
- W historii eksperymentów dodano kontrolki importu JSON i ponownego uruchomienia wybranego eksperymentu A.
- API: `POST /api/experiments/import` oraz `POST /api/experiments/{id}/rerun`.
- Wersja API: `2.5.0`.

Import przyjmuje pliki w formacie eksperymentu Qwantum VM, nie dowolne pliki JSON. Ponowne uruchomienie wykonuje nowe losowe pomiary, więc rozkład wyników może się różnić, szczególnie przy małej liczbie shots lub włączonym szumie.


## Nowości w wersji 2.6
- Automatyczny zapis bieżącej konfiguracji edytora w pamięci lokalnej przeglądarki (localStorage) oraz przycisk przywracania sesji.
- Porównanie rozkładów wyników dla dwóch wybranych eksperymentów w raporcie tabelarycznym.
- Eksport porównania A/B do pliku CSV, który można otworzyć w arkuszu kalkulacyjnym.
- API: `GET /api/experiments/compare/multi?ids=ID1,ID2` (od 2 do 20 eksperymentów) oraz `GET /api/experiments/compare/export.csv?a=ID1&b=ID2`.
- Wersja API: `2.6.0`.

Automatyczny zapis sesji dotyczy edytora w tej samej przeglądarce i na tym samym profilu; nie zastępuje zapisu projektu w bazie danych ani kopii zapasowej.


## Nowości w wersji 2.7
- Wizualizacja idealnej ewolucji stanu po każdej bramce obwodu.
- Wykresy prawdopodobieństw dla stanu początkowego i kolejnych etapów.
- Podgląd niezerowych amplitud zespolonych w każdym etapie.
- Endpoint API: `POST /api/statevector/evolution`.
- Wersja API: `2.7.0`.

Ewolucja korzysta z idealnego wektora stanu Qiskit i nie uwzględnia szumu ani pomiarów. Limit pozostaje na poziomie 8 kubitów.


## Nowości w wersji 2.8
- Porównanie rozkładów idealnych i zaszumionych po każdej bramce.
- Wykres porównawczy: niebieski oznacza wynik idealny, pomarańczowy — zaszumiony.
- Metryka TVD (total variation distance) pokazuje różnicę między rozkładami.
- Eksport raportu porównania do JSON z poziomu interfejsu.
- API: `POST /api/statevector/noise-evolution`.
- Wersja API: `2.8.0`.

Dla ograniczenia czasu działania raport dopuszcza maksymalnie 80 bramek i używa od 128 do 4096 pomiarów na etap. Wynik zaszumiony ma fluktuacje statystyczne. Jest to model szumu symulatora, nie kalibracja prawdziwego urządzenia.


## Nowości w wersji 2.9
- Analiza stabilności wyników przy różnych liczbach pomiarów (`shots`).
- Trzy niezależne próby dla każdej liczebności oraz raport średniej TVD i odchylenia standardowego.
- Panel w interfejsie z eksportem raportu `qwantum-shots-stability.json`.
- API: `POST /api/analysis/shots-stability`.
- Wersja API: `2.9.0`.

Analiza porównuje skończone próby z idealnym rozkładem i ilustruje fluktuacje statystyczne. Nie jest certyfikatem jakości fizycznego procesora. Limit: 40 bramek i do 4096 pomiarów na próbę.
