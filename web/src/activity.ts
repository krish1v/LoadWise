import { Dumbbell, Moon, Trophy } from "lucide-react";
import type { Activity } from "./api";

export const ACTIVITY: Record<Activity, { label: string; icon: typeof Dumbbell; next: Activity }> = {
  training: { label: "Training", icon: Dumbbell, next: "game" },
  game: { label: "Game", icon: Trophy, next: "rest" },
  rest: { label: "Rest", icon: Moon, next: "training" },
};
