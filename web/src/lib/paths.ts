import path from "path";

const ROOT = path.resolve(process.cwd(), "..");

export const PATHS = {
  root: ROOT,
  output: path.join(ROOT, "output"),
  briefs: path.join(ROOT, "output", "briefs"),
  requests: path.join(ROOT, "requests"),
  seedList: path.join(ROOT, "seed-list.json"),
  workflows: path.join(ROOT, "workflows"),
  env: path.join(ROOT, ".env"),
};
