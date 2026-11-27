using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

// PCClean 启动器：双击本 exe 会以管理员权限运行（由 app.manifest 的 requireAdministrator 保证），
// 然后调用 pythonw 运行同目录的 main.py。
class Program
{
    [STAThread]
    static int Main(string[] args)
    {
        string baseDir = AppDomain.CurrentDomain.BaseDirectory;
        string mainPy = Path.Combine(baseDir, "main.py");
        if (!File.Exists(mainPy))
        {
            MessageBox.Show("未找到 main.py。请把本程序放在 PCClean 软件目录下（与 main.py 同级）。",
                "PCClean", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        string pythonw = FindPythonw(baseDir);
        if (pythonw == null)
        {
            MessageBox.Show("未找到 Python。\n请安装 Python 3（勾选 Add to PATH），或使用打包好的独立版 PCClean.exe。",
                "PCClean", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        try
        {
            var psi = new ProcessStartInfo();
            psi.FileName = pythonw;
            psi.Arguments = "\"" + mainPy + "\"";
            psi.WorkingDirectory = baseDir;
            psi.UseShellExecute = false;
            Process.Start(psi);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show("启动失败：" + ex.Message, "PCClean", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static string FindPythonw(string baseDir)
    {
        // 1) 同目录的便携版 Python
        string p = Path.Combine(baseDir, "python", "pythonw.exe");
        if (File.Exists(p)) return p;

        // 2) PATH
        string pathEnv = Environment.GetEnvironmentVariable("PATH") ?? "";
        foreach (string dir in pathEnv.Split(';'))
        {
            if (string.IsNullOrWhiteSpace(dir)) continue;
            try
            {
                string cand = Path.Combine(dir.Trim().Trim('"'), "pythonw.exe");
                if (File.Exists(cand)) return cand;
            }
            catch { }
        }

        // 3) 用户级安装目录
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        string programs = Path.Combine(local, "Programs", "Python");
        if (Directory.Exists(programs))
        {
            foreach (string d in Directory.GetDirectories(programs, "Python*"))
            {
                string cand = Path.Combine(d, "pythonw.exe");
                if (File.Exists(cand)) return cand;
            }
        }

        // 4) 系统级安装目录
        foreach (string root in new[] { @"C:\Program Files\Python", @"C:\Program Files (x86)\Python" })
        {
            try
            {
                if (!Directory.Exists(root)) continue;
                foreach (string d in Directory.GetDirectories(root, "Python*"))
                {
                    string cand = Path.Combine(d, "pythonw.exe");
                    if (File.Exists(cand)) return cand;
                }
            }
            catch { }
        }
        return null;
    }
}
