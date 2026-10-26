/** UI-only state: which Learn-more page is open, the About dialog, and transient messages. */

import { create } from "zustand";

export interface UiState {
  learnMoreBlock: string | null;
  aboutOpen: boolean;
  toast: string | null;
  openLearnMore: (blockId: string) => void;
  closeLearnMore: () => void;
  setAbout: (open: boolean) => void;
  notify: (message: string | null) => void;
}

export const useUiStore = create<UiState>((set) => ({
  learnMoreBlock: null,
  aboutOpen: false,
  toast: null,
  openLearnMore: (blockId) => set({ learnMoreBlock: blockId }),
  closeLearnMore: () => set({ learnMoreBlock: null }),
  setAbout: (open) => set({ aboutOpen: open }),
  notify: (message) => set({ toast: message }),
}));
