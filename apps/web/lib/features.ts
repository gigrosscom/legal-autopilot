/** Lawyer catalogue and lawyer recruitment (/lawyers, /lawyers/request, /for-lawyers) and every link to them.
 * Off: the product positions itself as self-help without a lawyer; the pages answer 404. The lawyer's own
 * workspace (/lawyer) still opens by its address for lawyers who have already applied. */
export const LAWYERS_PUBLIC = false;

/** «Юрист по кнопке» — closed pilot (owner's decision 30.09.2026): in a case the client sees only the pilot lawyers the
 * owner picked in /ops (verified, with a price), sends a request, pays the accepted lawyer through the platform (to the
 * company's account) and the lawyer gets the case dossier. The public catalogue stays hidden (LAWYERS_PUBLIC). */
export const LAWYER_PILOT = true;
