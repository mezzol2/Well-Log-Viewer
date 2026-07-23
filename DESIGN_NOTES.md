# Design notes

Deeper background behind the [README](README.md): how the LAS reader copes
with real files, what the mock dataset actually contains, the security/QA
thinking behind the planned Claude integration, and the roadmap.

## Handling real-world LAS files

Real LAS files — unlike synthetic data — are inconsistent, incomplete, and
occasionally corrupt. `osdu_client/las_client.py` is written to survive
that rather than assume clean input:

- **Mnemonic aliases** — `RHOZ`/`DEN` → RHOB, `TNPH`/`NPOR` → NPHI,
  `ILD`/`LLD`/`RDEP` → RT, and a vendor-prefix case (`LFP_GR` → GR), so
  the standard display settings apply regardless of the source's naming.
  Every rename is surfaced in the curve-details panel so it can be
  audited (see [AI and the alias table](#ai-and-the-alias-table)).
- **Well-name normalization** — the same physical well is often spelled
  several ways across files (`NO_15/9-19_A` vs `15/9-19`), and some files
  name the wellbore while others name the parent well. Names are
  normalized using the Norwegian offshore convention (quadrant/block,
  well number, trailing sidetrack letter) so files describing one well
  group under a single well, with a wellbore per file. Unrecognized name
  formats pass through untouched rather than being guessed at.
- **Null values** (`-999.25`) — converted to gaps, not drawn as false
  lines across washout zones.
- **Wrapped files** — Volve-era LAS files are frequently wrapped; the
  reader uses the engine that handles them directly.
- **Corrupt / unreadable files** — reported as warnings, never allowed to
  crash the app; one bad file doesn't stop the rest from loading.
- **Missing headers** — sensible fallbacks (filename as well name,
  top-level folder as field when the `FLD` header is absent).
- **Many-curve files** — the curve picker lets you choose what to display;
  canonical curves (GR, RHOB, NPHI, RT) are ordered first.

## Mock dataset

The default synthetic dataset is 5 wells across 3 fields (Eldfisk, Ekofisk
— North Sea; Permian Basin — Texas), each with a generated composite log
(GR, RHOB, NPHI, RT).

It isn't random noise. Each log is built from randomly layered
sand/shale/carbonate facies, each facies with characteristic curve
responses, so sand, shale, and carbonate intervals show the physically
consistent crossovers between GR, RHOB, and NPHI that real facies-driven
logs exhibit. That makes it useful for exercising the display conventions
(e.g. NPHI/RHOB gas crossover) without any real data.

## Notes on building with an AI assistant

This project was scaffolded with Claude's help, which makes a few design
concerns worth stating explicitly.

### Security and IP

Once a Claude-powered QC / anomaly-detection step is added, be deliberate
about what leaves the machine:

- Send only **derived statistics or curve summaries** to the Claude API —
  never raw bulk curve arrays.
- Don't send OSDU data carrying PII or commercially sensitive identifiers
  without accounting for OSDU's own entitlements/ACL model.

The existing curve-details panel already computes the kind of summary
statistics (coverage, min/median/max, out-of-range flags) that such a step
would send — a deliberate choice so the QC pass can work without shipping
sample data off-machine.

### QA

Any LLM-based geological interpretation should be checked against a
**deterministic rule** (e.g. known sand/shale GR cutoffs) so you can
document where the model agreed or disagreed, rather than trusting it
blindly.

### AI and the alias table

The mnemonic alias table is a domain guess — the kind of thing an AI
assistant produces quickly but a petrophysicist should review. The
curve-details panel deliberately shows the original in-file mnemonic
alongside the renamed one, so every rename is visible and auditable in the
UI rather than silently applied.

## Roadmap

Suggested order:

1. **Claude-powered QC pass** — feed curve summary statistics (not raw
   arrays) to the Claude API and flag likely anomalies: unit mismatches,
   suspicious flat sections, out-of-range values.
2. **Well-header panel** — surface the LAS `~Well` section (operator,
   field, unique well ID, elevation, datum) when a well or wellbore is
   selected.
3. **`osdu_client/real_client.py`** — implement `OSDUClient` against a live
   OSDU instance once sandbox credentials are available.
