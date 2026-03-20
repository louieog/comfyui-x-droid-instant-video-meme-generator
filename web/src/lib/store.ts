import { create } from "zustand";
import type { ContentRequest, VideoOutput } from "./types";

interface AppState {
  outputs: VideoOutput[];
  requests: ContentRequest[];
  setOutputs: (o: VideoOutput[]) => void;
  setRequests: (r: ContentRequest[]) => void;
}

export const useStore = create<AppState>((set) => ({
  outputs: [],
  requests: [],
  setOutputs: (outputs) => set({ outputs }),
  setRequests: (requests) => set({ requests }),
}));
