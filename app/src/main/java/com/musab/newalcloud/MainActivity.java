package com.musab.newalcloud;
import android.app.Activity;
import android.os.Bundle;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
public class MainActivity extends Activity {
 WebView web; WebBridge bridge;
 @Override public void onCreate(Bundle b){super.onCreate(b);web=new WebView(this);web.setWebViewClient(new WebViewClient());WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);bridge=new WebBridge(this,web);web.addJavascriptInterface(bridge,"NewAlCloud");setContentView(web);web.loadUrl("file:///android_asset/index.html");}
 void js(String code){runOnUiThread(()->web.evaluateJavascript(code,null));}
 @Override public void onBackPressed(){if(web.canGoBack())web.goBack();else super.onBackPressed();}
}