# Upstream projects and compatibility notes

This implementation is a new starter framework and does not copy source files or ship proprietary engines from these repositories.

- https://github.com/nicholasgville23/LOTWPS — the LOTWPS repository supplied as the initial home for this framework.
- https://github.com/ruserprooyuncu-hub/noaa-weather-radio-simulator — feature reference for regional products, alert priority, station-local time, and a broadcast loop.
- https://github.com/dondaplayer1/weather-radio-suite — BMH-style product-generation and VoiceText Paul reference. Its upstream repository declares AGPL-3.0. Directly copying or deriving code from it requires preserving its license and complying with its terms; this starter is independently authored and does not bundle its code or WeatherRadioSuite-LIB assets.

VoiceText/NeoSpeech binaries and voice data are not included. Use software you are licensed to use. VTEditor_ENG.exe is a machine-local path and may be a GUI editor rather than a command-line synthesis engine. Use a documented CLI or SDK wrapper if available.
