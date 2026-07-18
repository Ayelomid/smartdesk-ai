"""Reproducible academic evaluation for the SmartDesk intent matcher."""
import csv
import json
import os
from collections import defaultdict
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, confusion_matrix
from predict import predict

TEST_CASES = [
    ("good morning support team", "greeting"), ("hello can you assist me", "greeting"),
    ("I cannot remember my sign in password", "password_reset"), ("my password has expired", "password_reset"),
    ("too many attempts locked me out", "account_locked"), ("my profile has been disabled", "account_locked"),
    ("authenticator is giving the wrong code", "two_factor_issue"), ("my verification text never came", "two_factor_issue"),
    ("the portal rejects my correct credentials", "login_problem"), ("I am signed out every few minutes", "login_problem"),
    ("wireless drops every few minutes", "network_issue"), ("I have no connection on my laptop", "network_issue"),
    ("remote access cannot establish a tunnel", "vpn_issue"), ("company VPN disconnects at home", "vpn_issue"),
    ("documents remain in the printing queue", "printer_problem"), ("the office printer appears offline", "printer_problem"),
    ("Outlook closes whenever I open it", "email_issue"), ("messages remain in my outbox", "email_issue"),
    ("Teams cannot detect my microphone", "audio_issue"), ("there is no audio from my headset", "audio_issue"),
    ("my video is black in Zoom", "camera_issue"), ("the webcam is unavailable", "camera_issue"),
    ("the program freezes after launch", "software_crash"), ("an application closes by itself", "software_crash"),
    ("I need approval to install Photoshop", "software_install"), ("please add a new application", "software_install"),
    ("the system update repeatedly fails", "windows_update"), ("Windows is stuck updating", "windows_update"),
    ("there is no room left on my drive", "storage_full"), ("I cannot save because storage is full", "storage_full"),
    ("the fan is loud and the case is hot", "overheating"), ("my notebook shuts off from heat", "overheating"),
    ("the PC displays a stop code", "blue_screen"), ("my computer is trapped in a boot loop", "blue_screen"),
    ("I entered my credentials on a fake page", "phishing"), ("I opened a suspicious attachment", "phishing"),
    ("antivirus says malware was found", "virus_malware"), ("ransomware encrypted my files", "virus_malware"),
    ("the laptop display is physically cracked", "hardware_fault"), ("several keyboard keys are broken", "hardware_fault"),
]

def evaluate():
    expected=[label for _,label in TEST_CASES]
    predicted=[predict(text)["intent"] for text,_ in TEST_CASES]
    labels=sorted(set(expected)|set(predicted))
    precision,recall,f1,_=precision_recall_fscore_support(expected,predicted,average="weighted",zero_division=0)
    results={"test_queries":len(expected),"classes":len(set(expected)),
      "accuracy":round(accuracy_score(expected,predicted),4),"precision_weighted":round(precision,4),
      "recall_weighted":round(recall,4),"f1_weighted":round(f1,4),
      "errors":[{"query":q,"expected":e,"predicted":p} for (q,e),p in zip(TEST_CASES,predicted) if e!=p]}
    out=os.path.join(os.path.dirname(__file__),"evaluation_results.json")
    with open(out,"w",encoding="utf-8") as f: json.dump(results,f,indent=2)
    matrix=confusion_matrix(expected,predicted,labels=labels)
    with open(os.path.join(os.path.dirname(__file__),"confusion_matrix.csv"),"w",newline="",encoding="utf-8") as f:
        writer=csv.writer(f); writer.writerow(["actual\\predicted",*labels])
        for label,row in zip(labels,matrix): writer.writerow([label,*row])
    print(json.dumps(results,indent=2))
    return results

if __name__ == "__main__": evaluate()
