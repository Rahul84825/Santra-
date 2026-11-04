# SANTRA Autonomous Architecture & ALEE Specifications

## Overview
SANTRA is an autonomous native AI desktop assistant for Windows 11 built with Python, PyQt6, SQLite, Faster-Whisper, and NVIDIA Nemotron.

## Subsystems
1. **Voice Pipeline:**
   - Faster-Whisper with INT8 compute and domain acoustic biasing.
   - SpeechListener with adaptive Voice Activity Detection (VAD).
   - Dynamic audio device hot-swapping and headset synchronization.

2. **Intelligence Routing:**
   - Layer 1: Instant local system reflexes (media, mute, lock, volume).
   - Layer 2: Deterministic OS automation and workspace execution.
   - Layer 3: NVIDIA Nemotron deep reasoning, ReAct agent loop, and Universal Research Engine.

3. **Autonomous Learning & Evolution Engine (ALEE):**
   - Zero-VRAM SQLite WAL store (`data/santra_evolution.db`).
   - Phonetic alias auto-promotion (`confidence_count >= 3`).
   - Hardware ResourceGuard protecting main thread, RAM headroom, and competitive 3D gaming.
   - Knowledge Explorer with FTS5 BM25 retrieval and adversarial prompt-injection defenses.

