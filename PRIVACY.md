# Privacy

PaperTrail is local-first. It sends no telemetry.

## Outbound network hosts
See the "Network" section of README.md. Every outbound call is opt-in and off by default;
the library and unit tests never touch the network.

## Personal data
Never commit real student data. Use `python -m papertrail.synth` to generate synthetic data.
Pseudonymise roll numbers in every exported example. Follow DPDP Act 2023 principles:
purpose limitation, minimisation and consent.
