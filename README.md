# QVirtual-Machine.Kbit777

**Qwantum VM 2.9** — lokalny symulator obwodów kwantowych oparty na Pythonie, FastAPI i Qiskit Aer.

## Uruchomienie w Windows 10/11

1. Otwórz folder repozytorium i pobierz jego zawartość: **Code → Download ZIP**.
2. Rozpakuj repozytorium.
3. Zainstaluj Python 3.12 64-bit.
4. Uruchom `install_windows.bat`.
5. Uruchom `run_windows.bat`.
6. Otwórz `http://127.0.0.1:8000`.

Testy uruchomisz przez `run_tests_windows.bat`.

## Główne funkcje w wersji 2.9

- Edytor obwodów z bramkami jedno- i dwukubitowymi.
- Wektor stanu i ewolucja stanu po kolejnych bramkach.
- Porównanie rozkładu idealnego z rozkładem zaszumionym oraz metryka TVD.
- Analiza stabilności pomiarów dla różnych wartości `shots`.
- Historia, import/eksport eksperymentów JSON i porównania CSV.
- Diagnostyka API i testy.

## Ograniczenia

To **symulator programowy**, a nie fizyczny procesor kwantowy. Limit wynosi 8 kubitów na obwód. Wizualizacja 777 węzłów nie oznacza 777 fizycznych kubitów. Model szumu jest uproszczony.

Składnia Pythona i JavaScript oraz integralność paczki zostały sprawdzone podczas przygotowania. Pełny zestaw testów z Qiskit Aer nie został potwierdzony w środowisku przygotowania, ponieważ ta biblioteka nie była w nim dostępna.
