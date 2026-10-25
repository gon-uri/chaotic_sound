/** The example patches (`examples/patches/`), bundled for the Examples menu. */

import type { PatchDocument } from "@chaotic-sound/engine";

const files = import.meta.glob<PatchDocument>("../../../examples/patches/*.json", {
  eager: true,
  import: "default",
});

export const EXAMPLES: readonly { name: string; patch: PatchDocument }[] = Object.entries(files)
  .map(([path, patch]) => ({ name: path.split("/").pop()!.replace(".json", ""), patch }))
  .sort((a, b) => a.name.localeCompare(b.name));
