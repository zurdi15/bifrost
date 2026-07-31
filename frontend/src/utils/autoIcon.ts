/** Candidate lookup names for a container's auto-icon, most specific first.
 * The hub matches them against the selfh.st index with flattening, so these
 * only need to vary the *words*, not the separators. */
export function iconCandidates(container: { name: string; image: string | null }): string[] {
  const out: string[] = [];
  const push = (raw: string | null | undefined): void => {
    const name = (raw ?? '').trim().toLowerCase();
    if (name && !out.includes(name)) out.push(name);
  };
  push(container.name);
  // Compose-style replica suffix: myproject-pihole-1 → myproject-pihole.
  push(container.name.replace(/[-_]\d+$/, ''));
  // Image basename: ghcr.io/rommapp/romm:4.6 → romm.
  push(container.image?.split('/').pop()?.split(':')[0]?.split('@')[0]);
  return out;
}
