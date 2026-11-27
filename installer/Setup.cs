using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;
using Microsoft.Win32;

// PCClean 单文件安装包：内嵌 payload.zip，安装到 Program Files，
// 创建桌面/开始菜单快捷方式，并在「程序和功能」中登记卸载信息。
// 支持参数：/target=路径  /silent  /noshortcut  /noreg
class Setup
{
    const string AppName = "全能磁盘清理专家";
    const string AppVersion = "1.3.1";

    [STAThread]
    static int Main(string[] args)
    {
        string target = null;
        bool silent = false, noShortcut = false, noReg = false;
        foreach (string raw in args)
        {
            string a = (raw ?? "").Trim();
            if (a.StartsWith("/target=", StringComparison.OrdinalIgnoreCase))
                target = a.Substring(8).Trim('"');
            else if (a.Equals("/silent", StringComparison.OrdinalIgnoreCase)) silent = true;
            else if (a.Equals("/noshortcut", StringComparison.OrdinalIgnoreCase)) noShortcut = true;
            else if (a.Equals("/noreg", StringComparison.OrdinalIgnoreCase)) noReg = true;
        }
        if (string.IsNullOrEmpty(target))
            target = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "PCClean");

        if (!silent)
        {
            DialogResult r = MessageBox.Show(
                "将把「" + AppName + " v" + AppVersion + "」安装到：\n\n" + target +
                "\n\n安装包已内置运行环境（无需另外安装 Python）。\n安装后可在「设置 → 应用」中卸载。\n\n是否继续？",
                "安装 " + AppName, MessageBoxButtons.YesNo, MessageBoxIcon.Question);
            if (r != DialogResult.Yes) return 0;
        }

        try
        {
            Directory.CreateDirectory(target);
            ExtractPayload(target);
        }
        catch (Exception ex)
        {
            if (silent) Console.Error.WriteLine("EXTRACT_FAIL: " + ex.Message);
            else MessageBox.Show("安装失败（解压程序文件出错）：\n\n" + ex.Message, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }

        string warn = "";
        if (!noShortcut)
        {
            try { CreateShortcuts(target); }
            catch (Exception ex) { warn += "\n- 创建快捷方式失败：" + ex.Message; }
        }
        if (!noReg)
        {
            try { RegisterUninstall(target); }
            catch (Exception ex) { warn += "\n- 写入卸载登记失败（不影响使用）：" + ex.Message; }
        }

        if (!silent)
        {
            string msg = "安装完成！\n\n位置：" + target;
            if (warn.Length > 0) msg += "\n\n注意：" + warn;
            msg += "\n\n是否立即启动「" + AppName + "」？";
            DialogResult r2 = MessageBox.Show(msg, "安装完成", MessageBoxButtons.YesNo, MessageBoxIcon.Information);
            if (r2 == DialogResult.Yes)
            {
                try { Process.Start(Path.Combine(target, "PCClean.exe")); } catch { }
            }
        }
        else if (warn.Length > 0)
        {
            Console.Error.WriteLine("WARN:" + warn);
        }
        return 0;
    }

    static void ExtractPayload(string target)
    {
        Assembly asm = Assembly.GetExecutingAssembly();
        string tmp = Path.Combine(Path.GetTempPath(), "pcclean_payload_" + Guid.NewGuid().ToString("N") + ".zip");
        try
        {
            using (Stream res = asm.GetManifestResourceStream("payload.zip"))
            {
                if (res == null) throw new Exception("安装包损坏：缺少内嵌数据");
                byte[] buf = new byte[81920];
                using (FileStream fs = File.Create(tmp))
                {
                    int n;
                    while ((n = res.Read(buf, 0, buf.Length)) > 0) fs.Write(buf, 0, n);
                }
            }
            Directory.CreateDirectory(target);
            if (!RunExtractTar(tmp, target) && !RunExtractPs(tmp, target))
                throw new Exception("解压失败（系统 tar 与 PowerShell 均不可用）");
        }
        finally
        {
            try { if (File.Exists(tmp)) File.Delete(tmp); } catch { }
        }
    }

    static bool RunExtractTar(string zip, string target)
    {
        try
        {
            string tar = Path.Combine(Environment.SystemDirectory, "tar.exe");
            if (!File.Exists(tar)) return false;
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = tar,
                Arguments = "-xf \"" + zip + "\" -C \"" + target + "\"",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardError = true,
                RedirectStandardOutput = true
            };
            using (Process p = Process.Start(psi))
            {
                p.WaitForExit(600000);
                return p.HasExited && p.ExitCode == 0;
            }
        }
        catch { return false; }
    }

    static bool RunExtractPs(string zip, string target)
    {
        try
        {
            string ps = "Expand-Archive -LiteralPath '" + zip.Replace("'", "''") +
                        "' -DestinationPath '" + target.Replace("'", "''") + "' -Force";
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"" + ps + "\"",
                UseShellExecute = false,
                CreateNoWindow = true
            };
            using (Process p = Process.Start(psi))
            {
                p.WaitForExit(600000);
                return p.HasExited && p.ExitCode == 0;
            }
        }
        catch { return false; }
    }

    static void CreateShortcuts(string installDir)
    {
        string exe = Path.Combine(installDir, "PCClean.exe");
        string desk = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string common = Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms);
        object wsh = Activator.CreateInstance(Type.GetTypeFromProgID("WScript.Shell"));
        MakeLnk(wsh, Path.Combine(desk, AppName + ".lnk"), exe, installDir);
        MakeLnk(wsh, Path.Combine(common, AppName + ".lnk"), exe, installDir);
    }

    static void MakeLnk(object wsh, string lnk, string target, string workDir)
    {
        object sc = wsh.GetType().InvokeMember("CreateShortcut", BindingFlags.InvokeMethod, null, wsh, new object[] { lnk });
        Type t = sc.GetType();
        t.InvokeMember("TargetPath", BindingFlags.SetProperty, null, sc, new object[] { target });
        t.InvokeMember("WorkingDirectory", BindingFlags.SetProperty, null, sc, new object[] { workDir });
        t.InvokeMember("IconLocation", BindingFlags.SetProperty, null, sc, new object[] { target + ",0" });
        t.InvokeMember("Description", BindingFlags.SetProperty, null, sc, new object[] { AppName });
        t.InvokeMember("Save", BindingFlags.InvokeMethod, null, sc, new object[] { });
    }

    static void RegisterUninstall(string installDir)
    {
        string key = @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PCClean";
        using (RegistryKey k = Registry.LocalMachine.CreateSubKey(key))
        {
            if (k == null) throw new Exception("无法写入注册表（权限不足）");
            k.SetValue("DisplayName", AppName);
            k.SetValue("DisplayVersion", AppVersion);
            k.SetValue("Publisher", "PCClean");
            k.SetValue("InstallLocation", installDir);
            k.SetValue("DisplayIcon", Path.Combine(installDir, "PCClean.exe") + ",0");
            k.SetValue("UninstallString", "\"" + Path.Combine(installDir, "Uninstall_PCClean.exe") + "\"");
            k.SetValue("InstallDate", DateTime.Now.ToString("yyyyMMdd"));
            k.SetValue("NoModify", 1, RegistryValueKind.DWord);
            k.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            try
            {
                long kb = DirSize(new DirectoryInfo(installDir)) / 1024;
                if (kb > int.MaxValue) kb = int.MaxValue;
                k.SetValue("EstimatedSize", (int)kb, RegistryValueKind.DWord);
            }
            catch { }
        }
    }

    static long DirSize(DirectoryInfo d)
    {
        long size = 0;
        FileInfo[] fis = d.GetFiles();
        foreach (FileInfo fi in fis) size += fi.Length;
        DirectoryInfo[] dis = d.GetDirectories();
        foreach (DirectoryInfo di in dis) { try { size += DirSize(di); } catch { } }
        return size;
    }
}
