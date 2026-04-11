/** True when saved LLM settings are sufficient for the selected backend (matches server env injection). */
export function hasLlmConfigured(llm: Record<string, unknown>): boolean {
  const backend = String(llm.backend || "openai")
    .trim()
    .toLowerCase();
  if (backend === "azure") {
    return (
      String(llm.azure_endpoint || "").trim() !== "" &&
      String(llm.azure_api_key || "").trim() !== "" &&
      String(llm.azure_deployment || "").trim() !== ""
    );
  }
  if (backend === "anthropic") {
    return (
      String(llm.anthropic_api_key || "").trim() !== "" &&
      String(llm.anthropic_model || "").trim() !== ""
    );
  }
  const key = String(llm.openai_api_key || "").trim();
  const model = String(llm.openai_model || "").trim();
  const base = String(llm.openai_base_url || "").trim();
  if (backend === "compatible") {
    return key !== "" && model !== "" && base !== "";
  }
  return key !== "" && model !== "";
}
