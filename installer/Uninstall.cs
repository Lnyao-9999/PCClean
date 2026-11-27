using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using Microsoft.Win32;

// PCClean 卸载器：删除快捷方式、注册表卸载登记、程序目录。
// /cleanup <dir> 为内部用法：由临时副本调用，删除安装目录后自删除。
class Uninstall
{
    const string AppName = "全能磁盘清理专家";

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length >= 2 && args[0].Equals("/cleanup", StringComparison.OrdinalIgnoreCase))
        {
            string d = args[1];
            System.Threading.Thread.Sleep(900);
            DeleteDir(d);
            SelfDelete();
            return 0;
        }

        bool silent = false;
        foreach (string a in args)
            if (a.Equals("/silent", StringComparison.OrdinalIgnoreCase)) silent = true;

        string dir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\');
        if (!silent)
        {
            DialogResult r = MessageBox.Show(
                "确定要卸载「" + AppName + "」吗？\n\n程序目录：" + dir +
                "\n\n（隔离区与历史记录位于 %LOCALAPPDATA%\\PCClean，默认保留，如需删除请手动删除）",
                "卸载 " + AppName, MessageBoxButtons.YesNo, MessageBoxIcon.Warning);
            if (r != DialogResult.Yes) return 0;
        }

        DeleteShortcuts();
        try
        {
            Registry.LocalMachine.DeleteSubKeyTree(
                @"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PCClean", false);
        }
        catch { }

        try
        {
            string self = Process.GetCurrentProcess().MainModule.FileName;
            string tmp = Path.Combine(Path.GetTempPath(), "PCClean_unins_" + Guid.NewGuid().ToString("N") + ".exe");
            File.Copy(self, tmp, true);
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = tmp,
                Arguments = "/cleanup \"" + dir + "\"",
                UseShellExecute = false,
                CreateNoWindow = true
            };
            Process.Start(psi);
            if (!silent)
                MessageBox.Show("已开始卸载，程序目录将在几秒内删除。", "卸载", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return 0;
        }
        catch (Exception ex)
        {
            if (!silent) MessageBox.Show("卸载失败：" + ex.Message, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static void DeleteShortcuts()
    {
        string desk = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
        string common = Environment.GetFolderPath(Environment.SpecialFolder.CommonPrograms);
        string userStart = Environment.GetFolderPath(Environment.SpecialFolder.Programs);
        string[] paths = new string[]
        {
            Path.Combine(desk, AppName + ".lnk"),
            Path.Combine(common, AppName + ".lnk"),
            Path.Combine(userStart, AppName + ".lnk")
        };
        foreach (string p in paths)
        {
            try { if (File.Exists(p)) File.Delete(p); } catch { }
        }
    }

    static void DeleteDir(string dir)
    {
        if (!Directory.Exists(dir)) return;
        for (int i = 0; i < 8; i++)
        {
            try { Directory.Delete(dir, true); return; }
            catch { System.Threading.Thread.Sleep(600); }
        }
    }

    static void SelfDelete()
    {
        try
        {
            string self = Process.GetCurrentProcess().MainModule.FileName;
            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = "cmd.exe",
                Arguments = "/c ping -n 2 127.0.0.1 >nul & del /f /q \"" + self + "\"",
                UseShellExecute = false,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden
            };
            Process.Start(psi);
        }
        catch { }
    }
}
