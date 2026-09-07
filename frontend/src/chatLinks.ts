import type { Source } from "./api";

// Claims are unstructured text: preserve numbers exactly and keep citations
// separate. An amount match cannot establish a field's sign, unit or identity.
export function claimParts(text: string, sources: Source[]) {
  const citations = sources.filter(
    (source, index) =>
      sources.findIndex(
        (other) =>
          other.document_id === source.document_id &&
          other.page === source.page &&
          other.block_id === source.block_id &&
          other.quote === source.quote,
      ) === index,
  );
  const parts: { text: string; sources: Source[] }[] = [];
  const normalize = (value: string) =>
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLocaleLowerCase("el-GR")
      .replace(/\s+/g, " ")
      .trim();
  for (const match of text.matchAll(/["«“]([^"»”\n]{3,100})["»”]/g)) {
    const phrase = match[1];
    // Numeric phrases must not imply a verified amount-to-source mapping.
    if (/\d/.test(phrase) || phrase.trim().split(/\s+/).length > 12) continue;
    const targets = citations.filter((source) =>
      normalize(source.quote || source.excerpt || "").includes(
        normalize(phrase),
      ),
    );
    if (!targets.length) continue;
    const start = match.index! + 1;
    parts.push({ text: text.slice(0, start), sources: [] });
    parts.push({ text: phrase, sources: targets });
    parts.push({ text: text.slice(start + phrase.length), sources: [] });
    return parts;
  }
  return [{ text, sources: [] }];
}
