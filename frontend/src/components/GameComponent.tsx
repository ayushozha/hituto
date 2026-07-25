import { useState, useEffect } from "react";
import { Mascot } from "./Mascot";
import WidgetCard from "./WidgetCard";

export interface MatchingContent {
  leftItems: string[];
  rightItems: string[];
  pairs: [string, string][];
}

export interface TriviaQuestion {
  question: string;
  options: string[];
  answer: string;
  explanation: string;
}

export interface GameComponentProps {
  gameType: "matching" | "trivia";
  topic: string;
  content: {
    leftItems?: string[];
    rightItems?: string[];
    pairs?: [string, string][];
    questions?: TriviaQuestion[];
  };
}

const BTN_PRIMARY =
  "btn-press w-full rounded-full bg-brand py-2.5 text-sm font-semibold text-white shadow-chip hover:brightness-105 disabled:opacity-40 disabled:shadow-none disabled:translate-y-0";

export default function GameComponent({ gameType, topic, content: rawContent }: GameComponentProps) {
  const content = rawContent ?? {};
  const [selectedLeft, setSelectedLeft] = useState<string | null>(null);
  const [selectedRight, setSelectedRight] = useState<string | null>(null);
  const [matchedPairs, setMatchedPairs] = useState<[string, string][]>([]);
  const [matchingError, setMatchingError] = useState<[string, string] | null>(null);

  const [triviaIndex, setTriviaIndex] = useState(0);
  const [triviaSelected, setTriviaSelected] = useState<number | null>(null);
  const [triviaSubmitted, setTriviaSubmitted] = useState(false);
  const [triviaScore, setTriviaScore] = useState(0);

  const [gameFinished, setGameFinished] = useState(false);

  const handleLeftClick = (item: string) => {
    if (matchedPairs.some(([l]) => l === item) || matchingError) return;
    setSelectedLeft(item);
  };

  const handleRightClick = (item: string) => {
    if (matchedPairs.some(([, r]) => r === item) || matchingError || !selectedLeft) return;
    setSelectedRight(item);

    const currentLeft = selectedLeft;
    const isPairMatch = content.pairs?.some(([l, r]) => l === currentLeft && r === item);

    if (isPairMatch) {
      setMatchedPairs((prev) => [...prev, [currentLeft, item]]);
      setSelectedLeft(null);
      setSelectedRight(null);
    } else {
      setMatchingError([currentLeft, item]);
      setTimeout(() => {
        setMatchingError(null);
        setSelectedLeft(null);
        setSelectedRight(null);
      }, 800);
    }
  };

  useEffect(() => {
    if (gameType === "matching" && content.pairs && matchedPairs.length === content.pairs.length) {
      setGameFinished(true);
    }
  }, [matchedPairs, gameType, content.pairs]);

  const handleTriviaSelect = (idx: number) => {
    if (triviaSubmitted) return;
    setTriviaSelected(idx);
  };

  const handleTriviaSubmit = () => {
    if (triviaSelected === null || triviaSubmitted) return;
    setTriviaSubmitted(true);
    const q = content.questions?.[triviaIndex];
    if (q && triviaSelected.toString() === q.answer) {
      setTriviaScore((prev) => prev + 1);
    }
  };

  const handleTriviaNext = () => {
    setTriviaSelected(null);
    setTriviaSubmitted(false);

    if (content.questions && triviaIndex + 1 < content.questions.length) {
      setTriviaIndex((prev) => prev + 1);
    } else {
      setGameFinished(true);
    }
  };

  const resetGame = () => {
    setSelectedLeft(null);
    setSelectedRight(null);
    setMatchedPairs([]);
    setMatchingError(null);
    setTriviaIndex(0);
    setTriviaSelected(null);
    setTriviaSubmitted(false);
    setTriviaScore(0);
    setGameFinished(false);
  };

  if (gameFinished) {
    const total = content.questions?.length ?? 0;
    const percentage = total > 0 ? Math.round((triviaScore / total) * 100) : 100;
    const strong = percentage >= 70;
    return (
      <div className="animate-pop-in w-full rounded-2xl border border-ink/5 bg-mint p-6 text-center text-ink shadow-chip">
        <Mascot mood="celebrate" className="mx-auto mb-3 h-20 w-20" title="Challenge complete" />
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-brand-dark">
          Challenge cleared
        </p>
        <h4 className="mt-1 font-archivo text-xl font-semibold tracking-tight">{topic}</h4>

        {gameType === "trivia" && content.questions && (
          <div className="my-5 flex items-center justify-around rounded-2xl border border-ink/5 bg-white p-4">
            <div>
              <div className="text-[10px] font-semibold uppercase text-ink-faint">Score</div>
              <div className="font-display text-xl font-semibold">
                {triviaScore} / {content.questions.length}
              </div>
            </div>
            <div className="h-7 w-px bg-line" />
            <div>
              <div className="text-[10px] font-semibold uppercase text-ink-faint">Accuracy</div>
              <div
                className={`mt-0.5 inline-flex rounded-full px-2.5 py-0.5 font-display text-lg font-semibold ${
                  strong ? "bg-mint text-lime-dark" : "bg-sand text-ink"
                }`}
              >
                {percentage}%
              </div>
            </div>
          </div>
        )}

        <p className="mt-4 px-4 text-[13px] font-medium leading-relaxed text-ink-soft">
          You reinforced the core ideas — ready for the next round whenever you are.
        </p>

        <button type="button" onClick={resetGame} className={`${BTN_PRIMARY} mt-6`}>
          Replay challenge
        </button>
      </div>
    );
  }

  const matchTotal = content.pairs?.length ?? 0;
  const matchProgress = matchTotal > 0 ? (matchedPairs.length / matchTotal) * 100 : 0;
  const triviaTotal = content.questions?.length ?? 1;

  return (
    <WidgetCard
      title={topic}
      eyebrow={gameType === "matching" ? "Matching board" : "Concept trivia"}
      pill={
        gameType === "matching"
          ? `${matchedPairs.length} of ${matchTotal}`
          : `${triviaIndex + 1} of ${triviaTotal}`
      }
      tone="game"
      className="select-none"
    >
      {gameType === "matching" && matchTotal > 0 && (
        <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-white/80">
          <div
            className="h-full rounded-full bg-lime transition-all duration-300"
            style={{ width: `${matchProgress}%` }}
          />
        </div>
      )}

      {gameType === "matching" && content.leftItems && content.rightItems && (
        <div>
          <p className="mb-4 rounded-2xl border border-ink/5 bg-white p-2.5 text-center text-xs font-medium leading-relaxed text-ink-soft">
            Pick a card on the left, then connect it to its match on the right.
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <div className="pl-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                Concept
              </div>
              {content.leftItems.map((item, idx) => {
                const isMatched = matchedPairs.some(([l]) => l === item);
                const isSelected = selectedLeft === item;
                const isErroneous = matchingError?.[0] === item;

                return (
                  <button
                    key={idx}
                    type="button"
                    disabled={isMatched}
                    onClick={() => handleLeftClick(item)}
                    className={`w-full rounded-2xl border p-3 text-left text-xs font-semibold transition duration-150 ${
                      isMatched
                        ? "border-lime/30 bg-mint text-lime-dark"
                        : isSelected
                          ? "border-brand bg-cream text-brand-dark"
                          : isErroneous
                            ? "animate-shake border-coral/20 bg-coral-soft text-coral-dark"
                            : "border-ink/5 bg-white text-ink hover:border-brand/30"
                    }`}
                  >
                    {item}
                  </button>
                );
              })}
            </div>

            <div className="space-y-2">
              <div className="pl-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
                Definition
              </div>
              {content.rightItems.map((item, idx) => {
                const isMatched = matchedPairs.some(([, r]) => r === item);
                const isSelected = selectedRight === item;
                const isErroneous = matchingError?.[1] === item;

                return (
                  <button
                    key={idx}
                    type="button"
                    disabled={isMatched || !selectedLeft}
                    onClick={() => handleRightClick(item)}
                    className={`w-full rounded-2xl border p-3 text-left text-xs font-semibold transition duration-150 ${
                      isMatched
                        ? "border-lime/30 bg-mint text-lime-dark"
                        : isSelected
                          ? "border-brand bg-cream text-brand-dark"
                          : isErroneous
                            ? "animate-shake border-coral/20 bg-coral-soft text-coral-dark"
                            : !selectedLeft
                              ? "cursor-not-allowed border-ink/5 bg-white/50 text-ink-faint"
                              : "border-ink/5 bg-white text-ink hover:border-brand/30"
                    }`}
                  >
                    {item}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {gameType === "trivia" && content.questions && content.questions[triviaIndex] && (
        <div>
          <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-white/80">
            <div
              className="h-full rounded-full bg-lime transition-all duration-300"
              style={{ width: `${((triviaIndex + 1) / triviaTotal) * 100}%` }}
            />
          </div>

          <div className="mb-2 flex items-center justify-between pl-1 text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            <span>
              Question {triviaIndex + 1} of {content.questions.length}
            </span>
            <span>Score: {triviaScore}</span>
          </div>

          <div className="mb-4">
            <p className="text-[15px] font-semibold leading-relaxed text-ink">
              {content.questions[triviaIndex].question}
            </p>
          </div>

          <div className="mb-4 space-y-2">
            {content.questions[triviaIndex].options.map((opt, oIdx) => {
              const isSelected = triviaSelected === oIdx;

              return (
                <button
                  key={oIdx}
                  type="button"
                  disabled={triviaSubmitted}
                  onClick={() => handleTriviaSelect(oIdx)}
                  className={`flex w-full items-center justify-between rounded-2xl border p-3 text-left text-xs font-semibold transition duration-150 ${
                    isSelected
                      ? "border-brand bg-cream text-brand-dark"
                      : "border-ink/5 bg-white text-ink hover:border-brand/30"
                  }`}
                >
                  <span>{opt}</span>
                  <span
                    className={`grid h-5 w-5 place-items-center rounded-full text-[10px] font-semibold ${
                      isSelected ? "bg-brand text-white" : "bg-sand text-ink-faint"
                    }`}
                  >
                    {isSelected ? "✓" : String.fromCharCode(65 + oIdx)}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="flex items-center gap-2 pt-1">
            {!triviaSubmitted ? (
              <button
                type="button"
                onClick={handleTriviaSubmit}
                disabled={triviaSelected === null}
                className={BTN_PRIMARY}
              >
                Submit response
              </button>
            ) : (
              <button type="button" onClick={handleTriviaNext} className={BTN_PRIMARY}>
                {triviaIndex + 1 < content.questions.length ? "Next question" : "Finish trivia"}
              </button>
            )}
          </div>

          {triviaSubmitted && (
            <div
              className={`mt-3 rounded-2xl p-3 text-xs font-medium leading-relaxed ${
                triviaSelected?.toString() === content.questions[triviaIndex].answer
                  ? "bg-mint text-lime-dark"
                  : "bg-coral-soft text-coral-dark"
              }`}
            >
              <div className="mb-1 font-semibold">
                {triviaSelected?.toString() === content.questions[triviaIndex].answer
                  ? "Correct!"
                  : `Not quite — the answer was: ${
                      content.questions[triviaIndex].options[
                        parseInt(content.questions[triviaIndex].answer)
                      ]
                    }`}
              </div>
              <p className="opacity-80">{content.questions[triviaIndex].explanation}</p>
            </div>
          )}
        </div>
      )}
    </WidgetCard>
  );
}
