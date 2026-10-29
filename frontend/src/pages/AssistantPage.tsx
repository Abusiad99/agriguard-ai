import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useLocale } from "@/context/LocaleContext";
import { assistantApi } from "@/lib/endpoints/assistant";
import { Card, PageHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { Icon } from "@/components/ui/Icon";
import { Textarea } from "@/components/ui/Input";
import { ApiError, type AssistantChatResponse, type AssistantSource } from "@/types/api";

interface Turn {
  role: "user" | "assistant";
  content: string;
  response?: AssistantChatResponse;
}

const MAX_CHARS = 2000;

export default function AssistantPage() {
  const { t, locale } = useLocale();
  const [params, setParams] = useSearchParams();
  const diagnosisId = params.get("diagnosis");
  const plantId = params.get("plant");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, pending]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const newChat = () => {
    abortRef.current?.abort();
    setTurns([]);
    setError(null);
    setPending(false);
  };

  const clearContext = () => {
    newChat();
    setParams({});
  };

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    const message = input.trim();
    if (!message || pending) return;
    if (message.length > MAX_CHARS) {
      setError(t.assistant.tooLong);
      return;
    }
    setError(null);
    setInput("");
    const history = turns.map((x) => ({ role: x.role, content: x.role === "assistant" ? x.response?.answer ?? "" : x.content }))
      .filter((x) => x.content).slice(-6);
    setTurns((prev) => [...prev, { role: "user", content: message }]);
    setPending(true);
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const response = await assistantApi.chat(
        { message, language: locale, history, diagnosis_id: diagnosisId, plant_profile_id: plantId },
        controller.signal
      );
      setTurns((prev) => [...prev, { role: "assistant", content: response.answer ?? "", response }]);
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      setError(err instanceof ApiError ? err.message : t.assistant.error);
      setTurns((prev) => prev.slice(0, -1));
      setInput(message);
    } finally {
      setPending(false);
    }
  };

  const contextText = diagnosisId ? t.assistant.contextDiagnosis : plantId ? t.assistant.contextPlant : t.assistant.contextNone;

  return (
    <div className="flex flex-col gap-5 stagger">
      <PageHeader
        title={t.assistant.title}
        subtitle={t.assistant.subtitle}
        actions={
          <Button variant="glass" icon="refresh" onClick={newChat} disabled={turns.length === 0 && !pending}>
            {t.assistant.newChat}
          </Button>
        }
      />

      <div className="glass flex flex-wrap items-center justify-between gap-3 rounded-2xl px-4 py-3 text-sm">
        <span className="flex items-center gap-2 text-muted">
          <Icon name="link" className="h-4 w-4" />
          <span className="font-semibold text-ink">{t.assistant.contextLabel}:</span>
          {diagnosisId ? <Link className="text-primary hover:underline" to={`/diagnoses/${diagnosisId}`}>{contextText}</Link>
            : plantId ? <Link className="text-primary hover:underline" to={`/plants/${plantId}`}>{contextText}</Link>
            : contextText}
        </span>
        {(diagnosisId || plantId) && (
          <Button variant="ghost" size="sm" icon="close" onClick={clearContext}>{t.assistant.clearContext}</Button>
        )}
      </div>

      <Card className="flex min-h-[24rem] flex-col gap-4">
        <div className="flex flex-1 flex-col gap-4" aria-live="polite">
          {turns.length === 0 && !pending && (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 py-10 text-center">
              <Icon name="chat" className="h-10 w-10 text-primary/60" />
              <p className="font-display text-lg font-semibold text-ink">{t.assistant.emptyTitle}</p>
              <p className="max-w-md text-sm text-muted">{t.assistant.emptyBody}</p>
            </div>
          )}
          {turns.map((turn, i) =>
            turn.role === "user" ? (
              <div key={i} className="ms-auto max-w-[85%] rounded-2xl rounded-ee-md bg-primary px-4 py-3 text-sm text-white">
                <p dir="auto" className="whitespace-pre-wrap text-start">{turn.content}</p>
              </div>
            ) : (
              <AssistantMessage key={i} response={turn.response!} />
            )
          )}
          {pending && (
            <div className="flex items-center gap-2 text-sm text-muted" role="status">
              <span className="h-2 w-2 animate-ping rounded-full bg-primary" />
              {t.assistant.thinking}
            </div>
          )}
          <div ref={endRef} />
        </div>

        {error && <Alert tone="error">{error}</Alert>}

        <form onSubmit={(e) => void send(e)} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Textarea
              rows={2}
              maxLength={MAX_CHARS}
              aria-label={t.assistant.placeholder}
              placeholder={t.assistant.placeholder}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
            />
          </div>
          <Button type="submit" icon="send" isLoading={pending} disabled={!input.trim()}>
            {t.assistant.send}
          </Button>
        </form>
        <p className="text-xs leading-relaxed text-muted">{t.assistant.disclaimer}</p>
      </Card>
    </div>
  );
}

function AssistantMessage({ response }: { response: AssistantChatResponse }) {
  const { t } = useLocale();
  const cited = new Set(response.citations);
  const sources = response.mode === "llm" ? response.sources.filter((s) => cited.has(s.id)) : response.sources;
  return (
    <div className="me-auto flex max-w-[95%] flex-col gap-3 rounded-2xl rounded-es-md border border-line/80 bg-surface/60 px-4 py-3 text-sm dark:bg-surface/30">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted">{t.assistant.modes[response.mode]}</p>
      {response.mode === "llm" && response.answer && (
        <p dir="auto" className="whitespace-pre-wrap text-start leading-relaxed text-ink">{response.answer}</p>
      )}
      {response.mode === "retrieval_only" && <p className="text-muted">{t.assistant.retrievalOnlyBody}</p>}
      {response.mode === "no_sources" && <p className="text-ink">{t.assistant.noSourcesBody}</p>}

      {response.notices.map((n) => (
        <p key={n} className="flex items-center gap-1.5 text-xs text-severity-mild">
          <Icon name="info" className="h-3.5 w-3.5" />
          {t.assistant.notices[n] ?? n}
        </p>
      ))}
      {response.mode === "llm" && !response.evidence_sufficient && <p className="text-xs text-severity-mild">{t.assistant.insufficient}</p>}
      {response.recommends_expert && <p className="text-xs text-muted">{t.assistant.expert}</p>}

      {response.context_used.model_result.length > 0 && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer font-medium">{t.assistant.modelResultUsed}</summary>
          <ul className="mt-1 list-disc ps-5">
            {response.context_used.model_result.map((m, i) => <li key={i} dir="ltr">{m}</li>)}
          </ul>
        </details>
      )}

      {sources.length > 0 && (
        <div>
          <p className="mb-2 text-xs font-semibold text-ink">{t.assistant.sources}</p>
          <ul className="flex flex-col gap-2">
            {sources.map((s) => <SourceItem key={s.id} source={s} showExcerpt={response.mode !== "llm"} />)}
          </ul>
        </div>
      )}
    </div>
  );
}

function SourceItem({ source, showExcerpt }: { source: AssistantSource; showExcerpt: boolean }) {
  const { t } = useLocale();
  const date = source.revised_date ?? source.published_date;
  return (
    <li className="rounded-xl bg-ink/[0.035] px-3 py-2.5">
      <details open={showExcerpt}>
        <summary className="cursor-pointer list-none">
          <span className="me-1.5 rounded-md bg-primary/10 px-1.5 py-0.5 font-data text-[11px] font-semibold text-primary-dark">{source.id}</span>
          <span dir="auto" className="font-medium text-ink">{source.title}</span>
          <span className="mt-0.5 block text-xs text-muted">
            {source.organization} · {t.assistant.sourceTypes[source.source_type] ?? source.source_type}
            {date && ` · ${source.revised_date ? t.assistant.revised : t.assistant.published} ${date}`}
          </span>
        </summary>
        <p dir="auto" className="mt-2 whitespace-pre-wrap text-start text-xs leading-relaxed text-ink">{source.excerpt}</p>
        {source.url && (
          <a href={source.url} target="_blank" rel="noopener noreferrer nofollow"
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline">
            {t.assistant.openSource}
            <Icon name="externalLink" className="h-3.5 w-3.5" />
          </a>
        )}
      </details>
    </li>
  );
}
