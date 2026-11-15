using System;
using System.Collections.Generic;
using System.Linq;

namespace Wirenook.Cass.Core
{
    /// <summary>What every upload of this avatar has to satisfy.</summary>
    public sealed class UploadPolicy
    {
        /// <summary>
        /// The description must mention at least one of these: where a player
        /// who likes the avatar can get its source, as the AGPL expects.
        /// </summary>
        public IReadOnlyList<string> DistributionMarkers = new[] { "github.com/CassidyPrather/cass-avatar" };

        /// <summary>Tags every upload carries, as VRChat stores them.</summary>
        public IReadOnlyList<string> RequiredTags = new[] { "author_tag_ai", "author_tag_agplv3" };

        public string ReleaseStatus = "public";
    }

    /// <summary>
    /// Checks an avatar record against the <see cref="UploadPolicy"/> before it
    /// is sent. These are guardrails against forgetting, not a lock: anyone
    /// who wants to upload differently can edit the policy or skip the check.
    /// </summary>
    public static class UploadGuard
    {
        /// <returns>One sentence per violation; empty when the record may be uploaded.</returns>
        public static List<string> Check(
            UploadPolicy policy,
            string name,
            string description,
            IEnumerable<string> tags,
            string releaseStatus)
        {
            var problems = new List<string>();

            if (string.IsNullOrWhiteSpace(name)) problems.Add("The avatar has no name.");

            var text = Plain(description);
            if (!policy.DistributionMarkers.Any(marker => text.IndexOf(marker, StringComparison.OrdinalIgnoreCase) >= 0))
            {
                problems.Add(
                    "The description must say where to get the avatar: include " +
                    string.Join(" or ", policy.DistributionMarkers) + ".");
            }

            var present = new HashSet<string>(tags ?? Enumerable.Empty<string>(), StringComparer.OrdinalIgnoreCase);
            foreach (var tag in policy.RequiredTags)
            {
                if (!present.Contains(tag)) problems.Add("The required tag " + tag + " is missing.");
            }

            if (!string.Equals(releaseStatus, policy.ReleaseStatus, StringComparison.OrdinalIgnoreCase))
            {
                problems.Add(
                    "The avatar must be " + policy.ReleaseStatus + ", but it is set to " +
                    (string.IsNullOrEmpty(releaseStatus) ? "nothing" : releaseStatus) + ".");
            }

            return problems;
        }

        /// <summary>
        /// Text as it was typed. VRChat stores descriptions with punctuation
        /// swapped for lookalike characters ("github․com⁄…"), so a record
        /// read back from it never contains the link literally. Four of the
        /// substitutes are replaced by name; the full-width ones (brackets,
        /// the at sign) fold back to ASCII under compatibility normalisation.
        /// </summary>
        public static string Plain(string text)
        {
            if (string.IsNullOrEmpty(text)) return "";
            return text
                .Replace('\u2024', '.') // one dot leader
                .Replace('\u2044', '/') // fraction slash
                .Replace('\u02F8', ':') // modifier letter raised colon
                .Replace('\u201A', ',') // single low-9 quotation mark
                .Normalize(System.Text.NormalizationForm.FormKC);
        }
    }
}
