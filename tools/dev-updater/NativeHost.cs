using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;

namespace SupremeFabWorks.AmazonOrderManagerDevUpdater
{
    public sealed class UpdateRequest
    {
        public string protocol { get; set; }
        public string action { get; set; }
        public string currentVersion { get; set; }
        public string extensionId { get; set; }
        public string reason { get; set; }
    }

    public sealed class UpdateResponse
    {
        public string protocol { get; set; }
        public bool ok { get; set; }
        public bool updated { get; set; }
        public string status { get; set; }
        public string currentVersion { get; set; }
        public string latestVersion { get; set; }
        public string installedVersion { get; set; }
        public string error { get; set; }
    }

    public sealed class ReleaseAsset
    {
        public string name { get; set; }
        public string browser_download_url { get; set; }
    }

    public sealed class ReleaseInfo
    {
        public string tag_name { get; set; }
        public bool draft { get; set; }
        public bool prerelease { get; set; }
        public List<ReleaseAsset> assets { get; set; }
    }

    public sealed class ManifestInfo
    {
        public string version { get; set; }
    }

    internal sealed class ReleaseCandidate
    {
        public ReleaseInfo Release { get; set; }
        public Version Version { get; set; }
    }

    public static class Program
    {
        private const string Protocol = "arl-dev-updater-v1";
        private const string HostName = "com.supremefabworks.amazon_order_manager_updater";
        private const string ExpectedExtensionId = "hhmimkpolikhncnbkkbbabbopbccabcf";
        private const string ExpectedOrigin = "chrome-extension://hhmimkpolikhncnbkkbbabbopbccabcf/";
        private const string ReleasesApi = "https://api.github.com/repos/supremefabworks-hub/Amazon-Order-Manager/releases?per_page=20";
        private const string ExtensionAssetName = "amazon-order-manager.zip";
        private const string ChecksumAssetName = "amazon-order-manager.zip.sha256";
        private static readonly JavaScriptSerializer Serializer = new JavaScriptSerializer();

        public static int Main(string[] args)
        {
            UpdateResponse response;
            try
            {
                ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;

                string callerOrigin = args != null && args.Length > 0 ? args[0] : null;
                if (!String.Equals(callerOrigin, ExpectedOrigin, StringComparison.Ordinal))
                    throw new InvalidOperationException("Caller origin is not authorized for this native host.");

                string json = ReadNativeMessage(Console.OpenStandardInput());
                UpdateRequest request = Serializer.Deserialize<UpdateRequest>(json);
                if (request == null || request.protocol != Protocol || request.action != "check_update")
                    throw new InvalidOperationException("Unsupported updater request.");
                if (!String.Equals(request.extensionId, ExpectedExtensionId, StringComparison.Ordinal))
                    throw new InvalidOperationException("Extension ID does not match the registered development build.");

                response = CheckForUpdate(request.currentVersion);
            }
            catch (Exception ex)
            {
                response = new UpdateResponse
                {
                    protocol = Protocol,
                    ok = false,
                    updated = false,
                    status = "error",
                    error = SafeError(ex)
                };
            }

            try
            {
                WriteNativeMessage(Console.OpenStandardOutput(), Serializer.Serialize(response));
                return response.ok ? 0 : 1;
            }
            catch
            {
                return 2;
            }
        }

        private static UpdateResponse CheckForUpdate(string currentVersionText)
        {
            Version currentVersion;
            if (!TryParseChromeVersion(currentVersionText, out currentVersion))
                throw new InvalidOperationException("Current extension version is invalid.");

            ReleaseCandidate candidate = FindLatestDevelopmentRelease();
            if (candidate == null)
            {
                return new UpdateResponse
                {
                    protocol = Protocol,
                    ok = true,
                    updated = false,
                    status = "no_release",
                    currentVersion = currentVersionText,
                    installedVersion = currentVersionText
                };
            }

            string latestVersionText = NormalizeVersion(candidate.Version);
            if (candidate.Version.CompareTo(currentVersion) <= 0)
            {
                return new UpdateResponse
                {
                    protocol = Protocol,
                    ok = true,
                    updated = false,
                    status = "up_to_date",
                    currentVersion = currentVersionText,
                    latestVersion = latestVersionText,
                    installedVersion = currentVersionText
                };
            }

            ReleaseAsset zipAsset = FindAsset(candidate.Release, ExtensionAssetName);
            ReleaseAsset checksumAsset = FindAsset(candidate.Release, ChecksumAssetName);
            if (zipAsset == null || checksumAsset == null)
                throw new InvalidOperationException("Latest development release is missing the extension ZIP or SHA-256 sidecar.");

            string tempRoot = Path.Combine(Path.GetTempPath(), "sfw-amazon-order-manager-update-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(tempRoot);
            try
            {
                string zipPath = Path.Combine(tempRoot, ExtensionAssetName);
                string checksumText = DownloadString(checksumAsset.browser_download_url);
                string expectedHash = ParseExpectedHash(checksumText);
                DownloadFile(zipAsset.browser_download_url, zipPath);

                string actualHash = ComputeSha256(zipPath);
                if (!String.Equals(expectedHash, actualHash, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidOperationException("Downloaded extension ZIP failed SHA-256 verification.");

                string extractRoot = Path.Combine(tempRoot, "extracted");
                Directory.CreateDirectory(extractRoot);
                ZipFile.ExtractToDirectory(zipPath, extractRoot);

                string packageRoot = LocateExtensionRoot(extractRoot);
                ValidatePackage(packageRoot, candidate.Version);
                InstallPackage(packageRoot);

                return new UpdateResponse
                {
                    protocol = Protocol,
                    ok = true,
                    updated = true,
                    status = "updated",
                    currentVersion = currentVersionText,
                    latestVersion = latestVersionText,
                    installedVersion = latestVersionText
                };
            }
            finally
            {
                try { if (Directory.Exists(tempRoot)) Directory.Delete(tempRoot, true); } catch { }
            }
        }

        private static ReleaseCandidate FindLatestDevelopmentRelease()
        {
            string json = DownloadString(ReleasesApi);
            List<ReleaseInfo> releases = Serializer.Deserialize<List<ReleaseInfo>>(json) ?? new List<ReleaseInfo>();
            ReleaseCandidate best = null;

            foreach (ReleaseInfo release in releases)
            {
                if (release == null || release.draft || !release.prerelease || String.IsNullOrWhiteSpace(release.tag_name))
                    continue;
                if (!release.tag_name.StartsWith("dev-v", StringComparison.Ordinal))
                    continue;

                Version version;
                if (!TryParseChromeVersion(release.tag_name.Substring(5), out version))
                    continue;

                if (best == null || version.CompareTo(best.Version) > 0)
                    best = new ReleaseCandidate { Release = release, Version = version };
            }

            return best;
        }

        private static ReleaseAsset FindAsset(ReleaseInfo release, string name)
        {
            if (release == null || release.assets == null) return null;
            foreach (ReleaseAsset asset in release.assets)
            {
                if (asset != null && String.Equals(asset.name, name, StringComparison.Ordinal) && !String.IsNullOrWhiteSpace(asset.browser_download_url))
                    return asset;
            }
            return null;
        }

        private static WebClient CreateWebClient()
        {
            WebClient client = new WebClient();
            client.Headers[HttpRequestHeader.UserAgent] = "SFW-Amazon-Order-Manager-Dev-Updater/1.0";
            client.Headers[HttpRequestHeader.Accept] = "application/vnd.github+json";
            return client;
        }

        private static string DownloadString(string url)
        {
            using (WebClient client = CreateWebClient())
                return client.DownloadString(url);
        }

        private static void DownloadFile(string url, string destination)
        {
            using (WebClient client = CreateWebClient())
                client.DownloadFile(url, destination);
        }

        private static string ParseExpectedHash(string text)
        {
            Match match = Regex.Match(text ?? String.Empty, @"(?i)\b[a-f0-9]{64}\b");
            if (!match.Success) throw new InvalidOperationException("SHA-256 sidecar did not contain a valid digest.");
            return match.Value.ToLowerInvariant();
        }

        private static string ComputeSha256(string path)
        {
            using (FileStream stream = File.OpenRead(path))
            using (SHA256 sha = SHA256.Create())
            {
                byte[] digest = sha.ComputeHash(stream);
                StringBuilder builder = new StringBuilder(digest.Length * 2);
                foreach (byte value in digest) builder.Append(value.ToString("x2"));
                return builder.ToString();
            }
        }

        private static string LocateExtensionRoot(string extractRoot)
        {
            string expected = Path.Combine(extractRoot, "amazon-order-manager");
            if (File.Exists(Path.Combine(expected, "manifest.json"))) return expected;
            if (File.Exists(Path.Combine(extractRoot, "manifest.json"))) return extractRoot;

            string[] manifests = Directory.GetFiles(extractRoot, "manifest.json", SearchOption.AllDirectories);
            if (manifests.Length != 1)
                throw new InvalidOperationException("Extension package must contain exactly one manifest.json root.");
            return Path.GetDirectoryName(manifests[0]);
        }

        private static void ValidatePackage(string packageRoot, Version expectedVersion)
        {
            string manifestPath = Path.Combine(packageRoot, "manifest.json");
            if (!File.Exists(manifestPath)) throw new InvalidOperationException("Downloaded package is missing manifest.json.");

            ManifestInfo manifest = Serializer.Deserialize<ManifestInfo>(File.ReadAllText(manifestPath, Encoding.UTF8));
            Version embeddedVersion;
            if (manifest == null || !TryParseChromeVersion(manifest.version, out embeddedVersion))
                throw new InvalidOperationException("Downloaded package has an invalid manifest version.");
            if (embeddedVersion.CompareTo(expectedVersion) != 0)
                throw new InvalidOperationException("Downloaded package version does not match its GitHub development release tag.");

            string[] requiredFiles = new string[]
            {
                "manifest.json", "service-worker.js", "background.js", "dev-updater.js", "content.js",
                "parser.js", "storage.js", "dashboard.html", "dashboard.js", "popup.html", "popup.js",
                "ui.css", "workflow-recorder.js"
            };
            foreach (string file in requiredFiles)
            {
                if (!File.Exists(Path.Combine(packageRoot, file)))
                    throw new InvalidOperationException("Downloaded package is missing required file: " + file);
            }
        }

        private static void InstallPackage(string packageRoot)
        {
            DirectoryInfo hostDirectory = new DirectoryInfo(AppDomain.CurrentDomain.BaseDirectory);
            DirectoryInfo installRoot = hostDirectory.Parent;
            if (installRoot == null) throw new InvalidOperationException("Unable to resolve updater installation root.");

            string current = Path.Combine(installRoot.FullName, "current");
            string previous = Path.Combine(installRoot.FullName, "previous");
            string next = Path.Combine(installRoot.FullName, ".next-" + Guid.NewGuid().ToString("N"));

            CopyDirectory(packageRoot, next);
            bool currentMoved = false;
            try
            {
                if (Directory.Exists(previous)) Directory.Delete(previous, true);
                if (Directory.Exists(current))
                {
                    Directory.Move(current, previous);
                    currentMoved = true;
                }
                Directory.Move(next, current);
            }
            catch
            {
                try { if (Directory.Exists(next)) Directory.Delete(next, true); } catch { }
                if (currentMoved && !Directory.Exists(current) && Directory.Exists(previous))
                {
                    try { Directory.Move(previous, current); } catch { }
                }
                throw;
            }
        }

        private static void CopyDirectory(string source, string destination)
        {
            Directory.CreateDirectory(destination);
            foreach (string file in Directory.GetFiles(source))
                File.Copy(file, Path.Combine(destination, Path.GetFileName(file)), true);
            foreach (string directory in Directory.GetDirectories(source))
                CopyDirectory(directory, Path.Combine(destination, Path.GetFileName(directory)));
        }

        private static bool TryParseChromeVersion(string text, out Version version)
        {
            version = null;
            if (String.IsNullOrWhiteSpace(text) || !Regex.IsMatch(text, @"^\d+(?:\.\d+){0,3}$")) return false;
            string[] fields = text.Split('.');
            int[] values = new int[] { 0, 0, 0, 0 };
            for (int i = 0; i < fields.Length; i++)
            {
                int value;
                if (!Int32.TryParse(fields[i], out value) || value < 0 || value > 65535) return false;
                values[i] = value;
            }
            version = new Version(values[0], values[1], values[2], values[3]);
            return true;
        }

        private static string NormalizeVersion(Version version)
        {
            if (version.Revision > 0) return String.Format("{0}.{1}.{2}.{3}", version.Major, version.Minor, version.Build, version.Revision);
            return String.Format("{0}.{1}.{2}", version.Major, version.Minor, version.Build);
        }

        private static string SafeError(Exception ex)
        {
            if (ex == null) return "Unknown updater error.";
            string message = ex.Message ?? ex.GetType().Name;
            return message.Length > 500 ? message.Substring(0, 500) : message;
        }

        private static string ReadNativeMessage(Stream input)
        {
            byte[] lengthBytes = ReadExact(input, 4);
            int length = BitConverter.ToInt32(lengthBytes, 0);
            if (length <= 0 || length > 64 * 1024 * 1024)
                throw new InvalidOperationException("Native message length is invalid.");
            byte[] payload = ReadExact(input, length);
            return Encoding.UTF8.GetString(payload);
        }

        private static void WriteNativeMessage(Stream output, string json)
        {
            byte[] payload = Encoding.UTF8.GetBytes(json ?? "{}");
            if (payload.Length > 1024 * 1024) throw new InvalidOperationException("Native response exceeds Chrome's maximum message size.");
            byte[] length = BitConverter.GetBytes(payload.Length);
            output.Write(length, 0, length.Length);
            output.Write(payload, 0, payload.Length);
            output.Flush();
        }

        private static byte[] ReadExact(Stream input, int count)
        {
            byte[] buffer = new byte[count];
            int offset = 0;
            while (offset < count)
            {
                int read = input.Read(buffer, offset, count - offset);
                if (read <= 0) throw new EndOfStreamException("Native message ended unexpectedly.");
                offset += read;
            }
            return buffer;
        }
    }
}
