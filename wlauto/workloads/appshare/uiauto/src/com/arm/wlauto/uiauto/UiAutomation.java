package com.arm.wlauto.uiauto.appshare;

import android.os.Bundle;

// Import the uiautomator libraries
import com.android.uiautomator.core.UiObject;
import com.android.uiautomator.core.UiScrollable;
import com.android.uiautomator.core.UiSelector;

import com.arm.wlauto.uiauto.UxPerfUiAutomation;

import static com.arm.wlauto.uiauto.BaseUiAutomation.FindByCriteria.BY_ID;
import static com.arm.wlauto.uiauto.BaseUiAutomation.FindByCriteria.BY_TEXT;
import static com.arm.wlauto.uiauto.BaseUiAutomation.FindByCriteria.BY_DESC;

import java.util.concurrent.TimeUnit;

public class UiAutomation extends UxPerfUiAutomation {

    // Create UIAutomation objects
    private com.arm.wlauto.uiauto.googlephotos.UiAutomation googlephotos =
        new com.arm.wlauto.uiauto.googlephotos.UiAutomation();

    private com.arm.wlauto.uiauto.gmail.UiAutomation gmail =
        new com.arm.wlauto.uiauto.gmail.UiAutomation();

    private com.arm.wlauto.uiauto.skype.UiAutomation skype =
        new com.arm.wlauto.uiauto.skype.UiAutomation();

    public Bundle parameters;

    public void runUiAutomation() throws Exception {
        // Override superclass value
        this.uiAutoTimeout = TimeUnit.SECONDS.toMillis(10);    
        parameters = getParams();

        // Setup the three uiautomator classes with the correct information
        // Also create a dummy parameter to disable marker api as they
        // should not log actions themselves.
        Bundle dummyParams = new Bundle();
        dummyParams.putString("markers_enabled", "false");
        googlephotos.parameters = dummyParams;
        googlephotos.packageName = parameters.getString("googlephotos_package");
        googlephotos.packageID = googlephotos.packageName + ":id/";
        gmail.parameters = dummyParams;
        gmail.packageName = parameters.getString("gmail_package");
        gmail.packageID = gmail.packageName + ":id/";
        skype.parameters = dummyParams;
        skype.packageName = parameters.getString("skype_package");
        skype.packageID = skype.packageName + ":id/";

        String recipient = parameters.getString("recipient");
        String loginName = parameters.getString("my_id");
        String loginPass = parameters.getString("my_pwd");
        String contactName = parameters.getString("name").replace("0space0", " ");

        setScreenOrientation(ScreenOrientation.NATURAL);

        setupGooglePhotos();
        sendToGmail(recipient);
        logIntoSkype(loginName, loginPass);
        // Skype won't allow us to login and share on first visit so invoke
        // once more from googlephotos
        pressBack();        
        sendToSkype(contactName);

        unsetScreenOrientation();
    }

    private void setupGooglePhotos() throws Exception {
        googlephotos.dismissWelcomeView();
        googlephotos.closePromotionPopUp();
        selectGalleryFolder("wa-working");
        googlephotos.selectFirstImage();
    }

    private void sendToGmail(String recipient) throws Exception {
        String gID = gmail.packageID;

        shareUsingApp("Gmail", "gmail");

        gmail.clearFirstRunDialogues();

        UiObject composeView =
            new UiObject(new UiSelector().resourceId(gID + "compose"));
        if (!composeView.waitForExists(uiAutoTimeout)) {
            // After the initial share request on some devices Gmail returns back
            // to the launching app, so we need to share the photo once more and
            // wait for Gmail to sync.
            shareUsingApp("Gmail", "gmail_retry");

            gmail.clearFirstRunDialogues();
        }

        gmail.setToField(recipient);
        gmail.setSubjectField();
        gmail.setComposeField();
        gmail.clickSendButton();
    }

    private void logIntoSkype(String loginName, String loginPass)  throws Exception {
        shareUsingApp("Skype", "skype_setup");

        skype.handleLoginScreen(loginName, loginPass);

        sleep(10); // Pause while the app settles before returning
    }

    private void sendToSkype(String contactName) throws Exception {
        shareUsingApp("Skype", "skype");

        skype.searchForContact(contactName);
        skype.dismissUpdatePopupIfPresent();

        sleep(10); // Pause while the app settles before returning
    }

    private void shareUsingApp(String appName, String tagName) throws Exception {
        String testTag = "share";
        ActionLogger logger = new ActionLogger(testTag + "_" + tagName, parameters);

        clickUiObject(BY_DESC, "Share", "android.widget.ImageView");
        UiScrollable applicationGrid =
            new UiScrollable(new UiSelector().resourceId(googlephotos.packageID + "application_grid"));
        UiObject openApp =
            new UiObject(new UiSelector().text(appName)
                                         .className("android.widget.TextView"));
        // On some devices the application_grid has many entries, se we have to swipe up to make
        // sure all the entries are visable.  This will also stop entries at the bottom being
        // obscured by the bottom action bar.
        applicationGrid.swipeUp(10);
        while (!openApp.exists()) {
            // In the rare case the grid is larger than the screen swipe up
            applicationGrid.swipeUp(10);
        }

        logger.start();
        openApp.clickAndWaitForNewWindow();
        logger.stop();
    }
}