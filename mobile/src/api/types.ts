/** Friendly names over the generated OpenAPI schema (src/api/schema.gen.ts). */
import type { components, operations } from './schema.gen';

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
/** Where a store click came from: the server rejects anything else (422). */
export type ClickSource = NonNullable<operations['outbound_v1_out__offer_id__get']['parameters']['query']>['src'];
export type ProductSummary = S['ProductSummary'];
export type SwipeReceipt = S['SwipeReceipt'];
export type SessionEntry = S['SessionCreate']['entry'];
