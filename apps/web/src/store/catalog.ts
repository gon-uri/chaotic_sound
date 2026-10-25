/** The system catalog, bundled with the app (it is the engine's data, ADR 0003). */

import { Catalog, type CatalogDocument } from "@chaotic-sound/engine";
import catalogJson from "../../../../catalog/systems.json";

export const catalogDocument = catalogJson as unknown as CatalogDocument;
export const catalog = new Catalog(catalogDocument);
