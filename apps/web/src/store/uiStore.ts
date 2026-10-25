/** UI-only state: which Learn-more page is open, and transient messages. */

import { create } from "zustand";

export interface UiState {
  learnMoreBlock: string | null;
  toast: string | null;
  openLearnMore: (blockId: string) => void;
  closeLearnMore: () => void;
  notify: (message: string | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  learnMoreBlock: null,
  toast: null,
  openLearnMore: (blockId) => set({ learnMoreBlock: blockId }),
  closeLearnMore: () => set({ learnMoreBlock: null }),
  notify: (message) => set({ toast: message }),
}));
