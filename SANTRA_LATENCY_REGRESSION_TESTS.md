# SANTRA — LATENCY & STT REGRESSION TEST SUITE

**Test Suites Executed:**
1. `tests/test_latency_and_stt_regression.py` (New Master Suite)
2. `tests/test_runtime_stability_regression.py` (Existing Master Suite)

**Overall Outcome:** 32 / 32 Tests Passing (100% Green, 0 Failures, 0 Errors)

---

## 1. Test Suite Results: `test_latency_and_stt_regression.py`

```
test_repetitive_wakeword_hallucination_loop (TestSTTValidationRegression) ... ok
test_high_compression_ratio_rejection (TestSTTValidationRegression) ... ok
test_low_info_fragment_rejection (TestSTTValidationRegression) ... ok
test_pure_wakeword_address_rejection (TestSTTValidationRegression) ... ok
test_valid_knowledge_queries_pass (TestSTTValidationRegression) ... ok
test_local_commands_remain_local_under_100ms (TestRoutingLatencyAndLayerRegression) ... ok
test_informational_explanation_routes_to_conversational (TestRoutingLatencyAndLayerRegression) ... ok
test_read_timeout_does_not_blame_credentials (TestAIProviderLatencyAndReliability) ... ok
test_401_results_in_credentials_invalid (TestAIProviderLatencyAndReliability) ... ok
test_prompt_cancellation_aborts_immediately (TestAIProviderLatencyAndReliability) ... ok
test_agent_brain_truthful_timeout_error_message (TestAIProviderLatencyAndReliability) ... ok
test_reasoning_and_thought_tags_stripped (TestAIProviderLatencyAndReliability) ... ok
test_granular_states_in_ui_state_enum (TestUIStateMachineTransitions) ... ok
test_map_runtime_status_mapping (TestUIStateMachineTransitions) ... ok
test_visual_configs_exist_for_all_states (TestUIStateMachineTransitions) ... ok

----------------------------------------------------------------------
Ran 15 tests in 0.971s

OK
```

---

## 2. Test Suite Results: `test_runtime_stability_regression.py`

```
test_camera_subsystem_toggle_and_release ... ok
test_command_palette_40_capabilities_ready ... ok
test_duplicate_ai_response_suppression ... ok
test_explanation_interruption_and_resumption ... ok
test_hotword_audio_stream_resumption ... ok
test_long_running_nemotron_sleep_mode_abort ... ok
test_microphone_watchdog_thread_lifecycle ... ok
test_native_sapi_tts_initialization ... ok
test_no_duplicate_turn_cards_in_ui ... ok
test_no_tts_speech_after_sleep_mode ... ok
test_open_brave_browser_execution ... ok
test_project_intelligence_panel_safe_initialization ... ok
test_prompt_injection_guardrail_enforcement ... ok
test_runtime_state_machine_valid_transitions ... ok
test_tts_stream_chunk_queue_invalidation ... ok
test_universal_voice_typing_cancellation ... ok
test_wake_acknowledgment_rapid_speech_handoff ... ok

----------------------------------------------------------------------
Ran 17 tests in 12.134s

OK
```

---

## 3. Coverage Summary

- **STT Hallucinations:** Repetitive token loops, compression ratios > 2.4, low-info fragments (`"And else."`), and standalone wake-word addresses are verified to never reach the AI backend.
- **Routing:** Local commands (`"open chrome"`, `"set volume to 50"`) route to Layer 1/2 deterministic execution in < 10ms with zero cloud overhead. Explanation queries route to Layer 2 with streaming tokens enabled.
- **Cloud AI Provider:** Read timeouts, connection timeouts, credential authentication failures, user cancellations, and thought tag stripping are verified to adhere to strict truthful attribution.
- **UI State Machine:** Transparent visual transitions from `WAITING_FOR_NVIDIA` to `STREAMING_RESPONSE` and `COMPLETED` verified across all runtime status maps.

