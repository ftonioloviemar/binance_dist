# OpenRouter Free Model Fallbacks

Last refreshed: 2026-05-17.

Source: OpenRouter public model catalog at `https://openrouter.ai/api/v1/models`.

## Runtime Rule

Use `OPENROUTER_MODELS` as the preferred ordered fallback list for AI target refinement.

- The list is best-to-worst for this repo's task: short JSON advice for portfolio target refinement.
- Separate model IDs with comma, semicolon, or newline.
- There is no hard count limit.
- Deprecated `MODEL_NAME`, `MODEL_FALLBACK`, and `MODEL_SECOND_FALLBACK` are used only when `OPENROUTER_MODELS` is absent.
- Free model availability can change; the bot now performs event-driven auto-curation when the first active model fails.

## Event-Driven Auto-Curation

The runtime does not refresh the full model list every day.

1. Use the first active model.
2. If it works, do nothing else.
3. If it fails, fall back through the remaining configured models.
4. After the run has a usable answer or safe fallback, refresh the OpenRouter free-model catalog.
5. Quarantine the failed primary model.
6. Rank useful free text models by known quality, JSON/structured-output support, context, and fit for conservative portfolio JSON advice.
7. Persist the reordered active list to `state/openrouter_models.json`.
8. On the next run, the registry takes precedence unless `OPENROUTER_MODELS_MODE=manual`.

This keeps normal runs light and only pays the model-refresh cost after a real degradation signal.

## Ordered Free List

1. `openrouter/owl-alpha`
2. `nvidia/nemotron-3-super-120b-a12b:free`
3. `deepseek/deepseek-v4-flash:free`
4. `qwen/qwen3-next-80b-a3b-instruct:free`
5. `google/gemma-4-31b-it:free`
6. `google/gemma-4-26b-a4b-it:free`
7. `openai/gpt-oss-120b:free`
8. `nousresearch/hermes-3-llama-3.1-405b:free`
9. `meta-llama/llama-3.3-70b-instruct:free`
10. `z-ai/glm-4.5-air:free`
11. `arcee-ai/trinity-large-thinking:free`
12. `minimax/minimax-m2.5:free`
13. `nvidia/nemotron-3-nano-30b-a3b:free`
14. `nvidia/nemotron-nano-9b-v2:free`
15. `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free`
16. `nvidia/nemotron-nano-12b-v2-vl:free`
17. `poolside/laguna-m.1:free`
18. `poolside/laguna-xs.2:free`
19. `baidu/cobuddy:free`
20. `openai/gpt-oss-20b:free`
21. `liquid/lfm-2.5-1.2b-thinking:free`
22. `liquid/lfm-2.5-1.2b-instruct:free`
23. `meta-llama/llama-3.2-3b-instruct:free`
24. `openrouter/free`

## Selection Notes

- Top priority goes to current free text models with large context and stronger instruction-following/reasoning fit.
- Models with explicit `response_format` or structured-output support are preferred because `portfolio.ai_refine_targets` asks for JSON.
- `openrouter/free` is kept last as a catch-all route because it is less deterministic than naming a concrete model.
- Music-oriented preview models and uncensored models were intentionally left out of the default chain because they are a poor fit for conservative financial JSON advice.
