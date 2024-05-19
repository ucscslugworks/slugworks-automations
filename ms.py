import sheet
from ms_active_directory import *

def login():
    print("starting ....")
    domain = ADDomain("au.ucsc.edu")
    print("domain connected")
    session = domain.create_session_as_user("username", "password")
    print("session created")
    return session



def add_user(session, to_add):
    session.add_users_to_groups(list(to_add), ["au-slugworks-access"])
    print("added users")




def remove_user(session, to_remove):
    session.remove_users_from_groups(list(to_remove), ["au-slugworks-access"])
    print("removed users")

def get_group(session):
    single_group_member_list = session.find_members_of_group("au-slugworks-access", ["cn"])
    print("group members found")

    in_group = []
    for user in single_group_member_list:

        # Access the attributes dictionary and get the value after 'cn'
        attributes = user.all_attributes
        cn_value = attributes["cn"]
        print(cn_value)
        in_group.append(cn_value)

    sheet.get_sheet_data(False)
    print("checking sheet data")
    All = sheet.student_data.loc[
        sheet.student_data["3D Printing"].isin(["Access", "Override Access"])
    ]["CruzID"].values.tolist()
    staff = sheet.staff_data["CruzID"].values.tolist()
    All = All + staff
    to_add = set(All) - set(in_group)
    to_remove = set(in_group) - set(All)
    return to_add, to_remove



def main():
    session = login()
    to_add, to_remove = get_group(session)
    add_user(session, to_add)
    remove_user(session, to_remove)
    print("done")
