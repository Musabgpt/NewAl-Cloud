package com.musab.newalcloud;
import android.webkit.JavascriptInterface;
import android.webkit.WebView;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
public final class WebBridge {
 private final MainActivity a; private final WebView web; private final RemoteChat chat=new RemoteChat(); private final ExecutorService pool=Executors.newSingleThreadExecutor();
 WebBridge(MainActivity a,WebView w){this.a=a;this.web=w;}
 @JavascriptInterface public void send(String prompt,String historyJson){
  pool.execute(()->{try{
   List<RemoteChat.Msg> ms=new ArrayList<>(); JSONArray h=new JSONArray(historyJson);
   for(int i=0;i<h.length();i++){JSONObject x=h.getJSONObject(i);ms.add(new RemoteChat.Msg(x.optString("role"),x.optString("content")));}
   ms.add(new RemoteChat.Msg("user",prompt));
   chat.chat(Providers.ENDPOINT,"",Providers.MODEL,ms,2048,0.7,d->a.js("window.onCloudDelta&&window.onCloudDelta("+JSONObject.quote(d)+")"));
   a.js("window.onCloudDone&&window.onCloudDone()");
  }catch(Exception e){a.js("window.onCloudError&&window.onCloudError("+JSONObject.quote(e.getMessage()==null?"خطأ":e.getMessage())+")");}});
 }
 @JavascriptInterface public void stop(){chat.cancel();}
}