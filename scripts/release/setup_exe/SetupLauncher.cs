// ScholarlyTranslation-Setup.exe: a self-extracting wrapper around the Setup zip.
//
// The release script compiles this file with the .NET Framework compiler that
// ships with Windows (csc.exe), embedding the Setup zip as the resource
// "payload.zip". At run time it extracts the zip into a fresh temporary
// folder, runs the same install.ps1 setup window that Install.bat runs (which
// installs into %LOCALAPPDATA%\ScholarlyTranslation because release.json is
// present), waits for it, and removes the temporary folder. It adds no install
// logic of its own and needs no administrator rights.
//
// C# 5 only (the in-box compiler): no string interpolation or ?. operators.

using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;

internal static class SetupLauncher
{
    private const string Title = "Scholarly Translation Setup";
    private const string PayloadName = "payload.zip";

    [STAThread]
    private static int Main()
    {
        string workDir = Path.Combine(Path.GetTempPath(), "ScholarlyTranslation-Setup-" + Guid.NewGuid().ToString("N"));
        try
        {
            string powershell = FindPowerShell();
            if (powershell == null)
            {
                ShowError("Windows PowerShell (powershell.exe) was not found on this computer. It is required to run the setup.\n\n" +
                          "לא נמצא Windows PowerShell במחשב. הוא נדרש להתקנה.");
                return 1;
            }

            Directory.CreateDirectory(workDir);
            Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream(PayloadName);
            if (payload == null)
            {
                ShowError("This setup file is damaged (the embedded application files are missing). Please download it again.");
                return 1;
            }
            using (payload)
            using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read))
            {
                string root = Path.GetFullPath(workDir) + Path.DirectorySeparatorChar;
                foreach (ZipArchiveEntry entry in archive.Entries)
                {
                    string target = Path.GetFullPath(Path.Combine(workDir, entry.FullName));
                    if (!target.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    {
                        throw new InvalidDataException("Unexpected path in the setup files: " + entry.FullName);
                    }
                    if (entry.FullName.EndsWith("/"))
                    {
                        Directory.CreateDirectory(target);
                        continue;
                    }
                    Directory.CreateDirectory(Path.GetDirectoryName(target));
                    entry.ExtractToFile(target, true);
                }
            }

            string script = Path.Combine(workDir, "install.ps1");
            if (!File.Exists(script) || !File.Exists(Path.Combine(workDir, "release.json")))
            {
                ShowError("This setup file is damaged (install.ps1 or release.json is missing). Please download it again.");
                return 1;
            }

            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = powershell;
            psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + script + "\"";
            psi.WorkingDirectory = workDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;  // install.ps1 shows its own setup window
            using (Process process = Process.Start(psi))
            {
                process.WaitForExit();
                int code = process.ExitCode;
                if (code != 0)
                {
                    ShowError("The setup window ended with an error (exit code " + code + ").\n\n" +
                              "חלון ההתקנה הסתיים עם שגיאה (קוד " + code + ").");
                }
                return code;
            }
        }
        catch (Exception ex)
        {
            ShowError("Setup could not start: " + ex.Message);
            return 1;
        }
        finally
        {
            try
            {
                if (Directory.Exists(workDir)) Directory.Delete(workDir, true);
            }
            catch (Exception)
            {
                // Best effort: Windows cleans the temporary folder eventually.
            }
        }
    }

    private static string FindPowerShell()
    {
        string system = Environment.GetFolderPath(Environment.SpecialFolder.System);
        string path = Path.Combine(system, @"WindowsPowerShell\v1.0\powershell.exe");
        return File.Exists(path) ? path : null;
    }

    private static void ShowError(string text)
    {
        MessageBox.Show(text, Title, MessageBoxButtons.OK, MessageBoxIcon.Error);
    }
}
