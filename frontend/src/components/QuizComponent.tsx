import { useState } from "react";
import WidgetCard from "./WidgetCard";
import { Mascot } from "./Mascot";

export interface QuizQuestion {
  type: "mcq" | "numeric" | "slider";
  title: string;
  prompt: string;
  explanation: string;
  options?: string[];
  correctAnswer: string;
  hints?: string[];
}

export interface QuizComponentProps {
  topic: string;
  questions?: QuizQuestion[] | null;
  /** Fired once when the quiz finishes. The voice instructor uses it to react aloud. */
  onResult?: (
    score: number,
    total: number,
    metadata?: { attempt: number; durationMs: number; hintUsed: boolean },
  ) => void;
  onRetry?: (attempt: number) => void;
}

/** Brand amber CTA — preferred over ink for this floating quiz. Lime stays on progress/correct. */
const BTN_PRIMARY =
  "btn-press flex-1 rounded-full bg-brand py-2.5 text-sm font-semibold text-white shadow-chip hover:brightness-105 disabled:opacity-40 disabled:shadow-none disabled:translate-y-0";

export default function QuizComponent({ topic, questions, onResult, onRetry }: QuizComponentProps) {
  const safeQuestions = Array.isArray(questions) ? questions : [];
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedOption, setSelectedOption] = useState<number | null>(null);
  const [numericAnswer, setNumericAnswer] = useState("");
  const [sliderAnswer, setSliderAnswer] = useState(5);
  const [showHint, setShowHint] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [isCorrect, setIsCorrect] = useState(false);
  const [score, setScore] = useState(0);
  const [quizFinished, setQuizFinished] = useState(false);
  const [attempt, setAttempt] = useState(1);
  const [startedAt, setStartedAt] = useState(() => Date.now());
  const [hintUsed, setHintUsed] = useState(false);

  const currentQuestion = safeQuestions[currentIndex];

  if (!currentQuestion) {
    return (
      <div className="rounded-2xl border border-ink/5 bg-surface p-4 text-sm font-semibold text-ink-soft">
        No quiz questions available.
      </div>
    );
  }

  const handleOptionSelect = (index: number) => {
    if (submitted) return;
    setSelectedOption(index);
  };

  const handleHintToggle = () => {
    setShowHint((prev) => !prev);
    setHintUsed(true);
  };

  const handleSubmit = () => {
    if (submitted) return;

    let correct = false;
    if (currentQuestion.type === "mcq") {
      correct = selectedOption?.toString() === currentQuestion.correctAnswer;
    } else if (currentQuestion.type === "numeric") {
      correct = numericAnswer.trim() === currentQuestion.correctAnswer.trim();
    } else if (currentQuestion.type === "slider") {
      correct = Math.abs(sliderAnswer - parseFloat(currentQuestion.correctAnswer)) <= 1;
    }

    setIsCorrect(correct);
    if (correct) {
      setScore((prev) => prev + 1);
    }
    setSubmitted(true);
  };

  const handleNext = () => {
    setSubmitted(false);
    setSelectedOption(null);
    setNumericAnswer("");
    setSliderAnswer(5);
    setShowHint(false);

    if (currentIndex + 1 < safeQuestions.length) {
      setCurrentIndex((prev) => prev + 1);
    } else {
      setQuizFinished(true);
      onResult?.(score, safeQuestions.length, {
        attempt,
        durationMs: Date.now() - startedAt,
        hintUsed,
      });
    }
  };

  if (quizFinished) {
    const percentage = Math.round((score / safeQuestions.length) * 100);
    const strong = percentage >= 70;
    return (
      <div className="animate-pop-in w-full rounded-2xl border border-ink/5 bg-pink-soft p-6 text-center text-ink shadow-chip">
        <Mascot mood="celebrate" className="mx-auto mb-3 h-20 w-20" title="Quiz complete" />
        <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-brand-dark">Nice work</p>
        <h4 className="mt-1 font-archivo text-xl font-semibold tracking-tight text-ink">
          {topic} complete!
        </h4>

        <div className="my-5 flex items-center justify-around rounded-2xl border border-ink/5 bg-white p-4">
          <div>
            <div className="text-[10px] font-semibold uppercase text-ink-faint">Score</div>
            <div className="font-display text-xl font-semibold text-ink">
              {score} / {safeQuestions.length}
            </div>
          </div>
          <div className="h-7 w-px bg-line" />
          <div>
            <div className="text-[10px] font-semibold uppercase text-ink-faint">Percentage</div>
            <div
              className={`mt-0.5 inline-flex rounded-full px-2.5 py-0.5 font-display text-lg font-semibold ${
                strong ? "bg-mint text-lime-dark" : "bg-sand text-ink"
              }`}
            >
              {percentage}%
            </div>
          </div>
        </div>

        <p className="px-2 text-[13px] font-medium leading-relaxed text-ink-soft">
          {strong
            ? "You’ve got this set of ideas locked in."
            : "Solid try — peek at the lesson again, then retake when you’re ready."}
        </p>

        <button
          type="button"
          onClick={() => {
            const nextAttempt = attempt + 1;
            setCurrentIndex(0);
            setScore(0);
            setQuizFinished(false);
            setSubmitted(false);
            setSelectedOption(null);
            setNumericAnswer("");
            setSliderAnswer(5);
            setShowHint(false);
            setHintUsed(false);
            setAttempt(nextAttempt);
            setStartedAt(Date.now());
            onRetry?.(nextAttempt);
          }}
          className="btn-press mt-5 w-full rounded-full bg-brand py-3 text-sm font-semibold text-white shadow-chip hover:brightness-105"
        >
          Retake quiz
        </button>
      </div>
    );
  }

  return (
    <WidgetCard
      title={topic}
      eyebrow={currentQuestion.title}
      pill={`${currentIndex + 1} of ${safeQuestions.length}`}
      tone="quiz"
    >
      <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-white/80">
        <div
          className="h-full rounded-full bg-lime transition-all duration-300"
          style={{ width: `${((currentIndex + 1) / safeQuestions.length) * 100}%` }}
        />
      </div>

      <div className="mb-5">
        <p className="text-[15px] font-semibold leading-relaxed text-ink">{currentQuestion.prompt}</p>
      </div>

      <div className="mb-4 space-y-2">
        {currentQuestion.type === "mcq" && currentQuestion.options && (
          <div className="grid gap-2">
            {currentQuestion.options.map((option, idx) => {
              const selected = selectedOption === idx;
              return (
                <button
                  key={idx}
                  type="button"
                  disabled={submitted}
                  onClick={() => handleOptionSelect(idx)}
                  className={`flex w-full items-center justify-between rounded-2xl border p-3 text-left text-sm font-semibold transition duration-150 ${
                    selected
                      ? "border-brand bg-cream text-brand-dark"
                      : "border-ink/5 bg-white text-ink hover:border-brand/30"
                  }`}
                >
                  <span>{option}</span>
                  <span
                    className={`grid h-5 w-5 place-items-center rounded-full text-[10px] font-semibold ${
                      selected ? "bg-brand text-white" : "bg-sand text-ink-faint"
                    }`}
                  >
                    {selected ? "✓" : String.fromCharCode(65 + idx)}
                  </span>
                </button>
              );
            })}
          </div>
        )}

        {currentQuestion.type === "numeric" && (
          <input
            type="text"
            disabled={submitted}
            value={numericAnswer}
            onChange={(e) => setNumericAnswer(e.target.value)}
            placeholder="Type your numeric answer…"
            className="h-11 w-full rounded-2xl border border-ink/10 bg-white px-3 text-sm font-semibold text-ink outline-none transition placeholder:text-ink-faint focus:border-ink/30 focus:ring-2 focus:ring-ink/10"
          />
        )}

        {currentQuestion.type === "slider" && (
          <div className="rounded-2xl border border-ink/5 bg-white px-3 py-4">
            <input
              type="range"
              min="0"
              max="10"
              step="1"
              disabled={submitted}
              value={sliderAnswer}
              onChange={(e) => setSliderAnswer(parseInt(e.target.value))}
              className="w-full cursor-pointer accent-brand"
            />
            <div className="mt-2 flex justify-between text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
              <span>0 · low</span>
              <span className="rounded-full bg-sand px-2 py-0.5 text-xs text-ink">Value: {sliderAnswer}</span>
              <span>10 · high</span>
            </div>
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 pt-1">
        {currentQuestion.hints && currentQuestion.hints.length > 0 && !submitted && (
          <button
            type="button"
            onClick={handleHintToggle}
            className="rounded-full border border-ink/10 bg-white px-4 py-2.5 text-xs font-semibold text-ink-soft transition hover:border-ink/20 hover:text-ink"
          >
            {showHint ? "Hide hint" : "Hint"}
          </button>
        )}

        {!submitted ? (
          <button
            type="button"
            onClick={handleSubmit}
            disabled={
              (currentQuestion.type === "mcq" && selectedOption === null) ||
              (currentQuestion.type === "numeric" && !numericAnswer.trim())
            }
            className={BTN_PRIMARY}
          >
            Submit answer
          </button>
        ) : (
          <button type="button" onClick={handleNext} className={BTN_PRIMARY}>
            {currentIndex + 1 < safeQuestions.length ? "Next question" : "Finish quiz"}
          </button>
        )}
      </div>

      {showHint && currentQuestion.hints && currentQuestion.hints.length > 0 && !submitted && (
        <div className="mt-3 rounded-2xl border border-ink/5 bg-white p-3 text-xs font-medium leading-relaxed text-ink">
          <strong className="font-semibold">Hint:</strong> {currentQuestion.hints[0]}
        </div>
      )}

      {submitted && (
        <div
          className={`mt-3 rounded-2xl p-3 text-xs font-medium leading-relaxed ${
            isCorrect ? "bg-mint text-lime-dark" : "bg-coral-soft text-coral-dark"
          }`}
        >
          <div className="mb-1 font-semibold">
            {isCorrect
              ? "Correct!"
              : `Not quite — the answer was: ${
                  currentQuestion.type === "mcq" && currentQuestion.options
                    ? currentQuestion.options[parseInt(currentQuestion.correctAnswer)]
                    : currentQuestion.correctAnswer
                }`}
          </div>
          <p className="opacity-80">{currentQuestion.explanation}</p>
        </div>
      )}
    </WidgetCard>
  );
}
