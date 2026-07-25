import React, { useState } from "react";
import WidgetCard from "./WidgetCard";

export interface Flashcard {
  front: string;
  back: string;
}

export interface FlipCardComponentProps {
  topic: string;
  cards: Flashcard[];
}

export default function FlipCardComponent({ topic, cards }: FlipCardComponentProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);

  if (!cards || cards.length === 0) {
    return (
      <div className="rounded-2xl border border-ink/5 bg-surface p-4 text-center text-xs font-semibold text-ink-soft">
        No flashcards available.
      </div>
    );
  }

  const currentCard = cards[currentIndex];

  const handleFlip = () => {
    setIsFlipped((prev) => !prev);
  };

  const handlePrev = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsFlipped(false);
    setTimeout(() => {
      setCurrentIndex((prev) => (prev > 0 ? prev - 1 : cards.length - 1));
    }, 150);
  };

  const handleNext = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsFlipped(false);
    setTimeout(() => {
      setCurrentIndex((prev) => (prev < cards.length - 1 ? prev + 1 : 0));
    }, 150);
  };

  return (
    <WidgetCard
      title={topic}
      eyebrow="Flashcard deck"
      pill={`${currentIndex + 1} of ${cards.length}`}
      tone="flashcards"
      className="select-none"
      footer={
        <div className="flex items-center justify-between gap-2">
          <button
            type="button"
            onClick={handlePrev}
            aria-label="Previous flashcard"
            className="rounded-full border border-ink/10 bg-white px-3.5 py-2 text-xs font-semibold text-ink-soft transition hover:border-brand/30 hover:text-ink"
          >
            ← Prev
          </button>
          <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-faint">
            Tap to flip
          </span>
          <button
            type="button"
            onClick={handleNext}
            aria-label="Next flashcard"
            className="btn-press rounded-full bg-brand px-3.5 py-2 text-xs font-semibold text-white shadow-chip hover:brightness-105"
          >
            Next →
          </button>
        </div>
      }
    >
      <div className="mb-3 h-1.5 w-full overflow-hidden rounded-full bg-white/80">
        <div
          className="h-full rounded-full bg-lime transition-all duration-300"
          style={{ width: `${((currentIndex + 1) / cards.length) * 100}%` }}
        />
      </div>

      <button
        type="button"
        className="group mb-1 h-44 w-full cursor-pointer [perspective:1000px]"
        onClick={handleFlip}
        aria-label={isFlipped ? "Flip flashcard back to question" : "Reveal flashcard answer"}
      >
        <div
          className={`relative h-full w-full text-center transition-transform duration-500 [transform-style:preserve-3d] ${
            isFlipped ? "[transform:rotateY(180deg)]" : ""
          }`}
        >
          <div className="absolute inset-0 flex h-full w-full flex-col items-center justify-center rounded-2xl border border-ink/5 bg-white p-6 [backface-visibility:hidden]">
            <span className="material-symbols-outlined mb-2 text-lg text-brand" aria-hidden="true">
              help
            </span>
            <p className="max-h-24 overflow-y-auto px-1 text-[15px] font-semibold leading-relaxed text-ink">
              {currentCard.front}
            </p>
            <span className="absolute bottom-3 text-[9px] font-semibold uppercase tracking-widest text-ink-faint">
              Click to reveal
            </span>
          </div>

          <div className="absolute inset-0 flex h-full w-full flex-col items-center justify-center rounded-2xl border border-brand/20 bg-cream p-6 text-brand-dark [backface-visibility:hidden] [transform:rotateY(180deg)]">
            <span className="material-symbols-outlined mb-2 text-lg text-brand" aria-hidden="true">
              auto_awesome
            </span>
            <p className="max-h-24 overflow-y-auto px-1 text-[13px] font-semibold leading-relaxed">
              {currentCard.back}
            </p>
            <span className="absolute bottom-3 text-[9px] font-semibold uppercase tracking-widest text-brand-dark/50">
              Click to flip back
            </span>
          </div>
        </div>
      </button>
    </WidgetCard>
  );
}
