/**
 * "Questions à poser" - a standard rubric shown at the bottom of every
 * module, not just Technology. Two sources feed it, both already computed
 * elsewhere (nothing invented here):
 *  - questions the trigger engine generated when a cross-module signal fired
 *    (currently only Technology's dependency trigger produces these)
 *  - the `resolving_information` field already carried by every red flag
 *    tagged with this module's category ("what would resolve this flag" is,
 *    in practice, exactly a question to ask)
 * Grouped by category so it doesn't read as one flat undifferentiated list.
 */
import { RedFlag } from "@/lib/api";

const CATEGORY_LABEL: Record<string, string> = {
  market: "Marché",
  market_dynamics: "Dynamique de marché",
  competition: "Concurrence",
  moat: "Moat",
  technology: "Technologie",
  traction: "Traction",
  financial: "Financier",
  business_model: "Business model",
  team: "Équipe",
  founders: "Équipe",
};

export default function QuestionsToAsk({ moduleKey, redFlags, extraQuestions }: { moduleKey: string; redFlags: RedFlag[]; extraQuestions?: string[] }) {
  const fromFlags = redFlags.filter((f) => f.category === moduleKey && f.resolving_information);
  const groups = new Map<string, string[]>();
  if (extraQuestions && extraQuestions.length > 0) {
    groups.set(moduleKey, [...extraQuestions]);
  }
  for (const f of fromFlags) {
    const key = f.category || moduleKey;
    const list = groups.get(key) || [];
    if (f.resolving_information && !list.includes(f.resolving_information)) list.push(f.resolving_information);
    groups.set(key, list);
  }

  if (groups.size === 0) return null;

  return (
    <div className="questions-to-ask">
      <div className="questions-to-ask-heading">Questions à poser</div>
      {Array.from(groups.entries()).map(([cat, qs]) => (
        <div key={cat} className="questions-group">
          {groups.size > 1 && <div className="questions-group-label">{CATEGORY_LABEL[cat] || cat}</div>}
          <ul>
            {qs.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
