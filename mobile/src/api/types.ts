/** Friendly names over the generated OpenAPI schema (src/api/schema.gen.ts). */
import type { components } from './schema.gen';

type S = components['schemas'];

export type SignInResult = S['SignInResult'];
export type TokenPair = S['TokenPair'];
export type UserProfile = S['UserProfile'];
export type AppConfig = S['AppConfig'];
export type SessionView = S['SessionView'];
export type ActionResult = S['ActionResult'];
export type BoardSummary = S['BoardSummary'];
export type BoardView = S['BoardView'];
export type StyleProfileView = S['StyleProfileView'];
export type StyleOptions = S['StyleOptions'];
export type ProductSummary = S['ProductSummary'];
export type SwipeReceipt = S['SwipeReceipt'];
export type SessionEntry = S['SessionCreate']['entry'];
