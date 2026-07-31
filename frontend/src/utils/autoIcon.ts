/** Candidate lookup names for a service's auto-icon, most specific first.
 * The hub matches them against the selfh.st index with flattening, so these
 * only need to vary the *words*, not the separators. */
export function iconCandidates(subject: {
  name: string;
  image?: string | null;
  meta?: { name?: string };
}): string[] {
  const out: string[] = [];
  const push = (raw: string | null | undefined): void => {
    const name = (raw ?? '').trim().toLowerCase();
    if (name && !out.includes(name)) out.push(name);
  };
  // A custom display name is the user telling us what this service IS.
  push(subject.meta?.name);
  push(subject.name);
  // Compose-style replica suffix: myproject-pihole-1 → myproject-pihole.
  push(subject.name.replace(/[-_]\d+$/, ''));
  // Image basename: ghcr.io/rommapp/romm:4.6 → romm.
  push(subject.image?.split('/').pop()?.split(':')[0]?.split('@')[0]);
  return out;
}
