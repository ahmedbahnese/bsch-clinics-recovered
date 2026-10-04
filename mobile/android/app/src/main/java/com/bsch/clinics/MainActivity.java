package com.bsch.clinics;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public class MainActivity extends Activity {
    private WebView web;
    private String pendingBackup;
    private static final int CREATE_BACKUP = 41;
    private static final int OPEN_BACKUP = 42;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setUserAgentString(settings.getUserAgentString() + " BSCHClinicsOffline/1.0");
        web.setWebViewClient(new WebViewClient());
        web.addJavascriptInterface(new OfflineBridge(), "AndroidBridge");
        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");
    }

    public class OfflineBridge {
        @JavascriptInterface public void saveBackup(String json) {
            pendingBackup = json;
            Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType("application/json");
            i.putExtra(Intent.EXTRA_TITLE, "bsch-clinics-backup.json");
            startActivityForResult(i, CREATE_BACKUP);
        }
        @JavascriptInterface public void pickBackup() {
            Intent i = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType("application/json");
            startActivityForResult(i, OPEN_BACKUP);
        }
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null) return;
        Uri uri = data.getData();
        try {
            if (requestCode == CREATE_BACKUP && pendingBackup != null) {
                OutputStream out = getContentResolver().openOutputStream(uri);
                out.write(pendingBackup.getBytes(StandardCharsets.UTF_8));
                out.close();
                Toast.makeText(this, "تم حفظ النسخة الاحتياطية", Toast.LENGTH_LONG).show();
            } else if (requestCode == OPEN_BACKUP) {
                InputStream in = getContentResolver().openInputStream(uri);
                BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8));
                StringBuilder text = new StringBuilder(); String line;
                while ((line = reader.readLine()) != null) text.append(line);
                reader.close();
                web.evaluateJavascript("window.importBackup(" + JSONObject.quote(text.toString()) + ")", null);
            }
        } catch (Exception e) {
            Toast.makeText(this, "تعذر التعامل مع ملف النسخة الاحتياطية", Toast.LENGTH_LONG).show();
        }
    }

    @Override public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }
}
