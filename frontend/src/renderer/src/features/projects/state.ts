import { create } from "zustand";
export const useUi = create<{
  archived: boolean;
  setArchived: (value: boolean) => void;
}>((set) => ({
  archived: false,
  setArchived: (archived) => set({ archived }),
}));
