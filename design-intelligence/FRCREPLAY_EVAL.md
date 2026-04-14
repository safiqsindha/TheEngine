# FRCReplay Adoption Evaluation

## What It Does
FRCReplay is a lightweight Python automation tool that integrates with OBS (Open Broadcaster Software) to capture, organize, and save match video recordings automatically during FRC events. Upon robot connection, it triggers recording; when matches conclude, it stops and saves the file to a local folder, eliminating manual recording management.

## Layer & Language
- **Layer**: Match operations / event infrastructure (not robot code, not scouting analytics)
- **Language**: Python (99.7%), with batch script support
- **Audience**: Event organizers, film crew, post-match review

## License & Maintenance
- **License**: Not specified in repository (no LICENSE file detected)
- **Last Commit**: June 8, 2025 (very recent)
- **Activity**: Minimal—only 2 commits on main branch; 0 stars, 0 forks, 0 issues
- **Status**: Early-stage prototype; appears archived or dormant despite recent timestamp

## Verdict: **CUT**
FRCReplay solves an operational problem (automated match recording) that is orthogonal to The Engine's core mission of robot intelligence, alliance strategy, and scouting. While useful for event logistics, it lacks maintenance momentum, has no community adoption, and adds complexity without ROI for design/strategy workflows. AdvantageKit (Java, 248⭐) is the established standard for FRC replay/logging and integrates directly with robot code—a fundamentally different use case.

## Why Not Adopt
1. **Scope mismatch**: Handles video capture, not data analysis or strategy
2. **Maintenance risk**: Minimal activity and no license declaration raise adoption friction
3. **Operational focus**: Solves a film crew problem, not an engineering analysis problem
4. **AdvantageKit dominance**: If replay is needed for robot logic, AdvantageKit is the proven choice (deterministic log replay for simulation & analysis)

## Study Opportunity
If The Engine ever needs to archive competition footage programmatically (e.g., for automated highlight reels or post-event analysis), study FRCReplay's OBS integration pattern as a reference for future video-pipeline work.
