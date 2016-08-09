/* AUTO-GENERATED FILE.  DO NOT MODIFY.
 *
 * This class was automatically generated by the
 * java mavlink generator tool. It should not be modified by hand.
 */

// MESSAGE HEARTBEAT_ICAROUS PACKING
package com.MAVLink.icarous;
import com.MAVLink.MAVLinkPacket;
import com.MAVLink.Messages.MAVLinkMessage;
import com.MAVLink.Messages.MAVLinkPayload;
        
/**
* ICAROUS heartbeat
*/
public class msg_heartbeat_icarous extends MAVLinkMessage{

    public static final int MAVLINK_MSG_ID_HEARTBEAT_ICAROUS = 229;
    public static final int MAVLINK_MSG_LENGTH = 1;
    private static final long serialVersionUID = MAVLINK_MSG_ID_HEARTBEAT_ICAROUS;


      
    /**
    * FMS state (0-idle, 1-Takeoff, 2-Climb, 3-Cruise, 4-Land)
    */
    public byte status;
    

    /**
    * Generates the payload for a mavlink message for a message of this type
    * @return
    */
    public MAVLinkPacket pack(){
        MAVLinkPacket packet = new MAVLinkPacket(MAVLINK_MSG_LENGTH);
        packet.sysid = 255;
        packet.compid = 190;
        packet.msgid = MAVLINK_MSG_ID_HEARTBEAT_ICAROUS;
              
        packet.payload.putByte(status);
        
        return packet;
    }

    /**
    * Decode a heartbeat_icarous message into this class fields
    *
    * @param payload The message to decode
    */
    public void unpack(MAVLinkPayload payload) {
        payload.resetIndex();
              
        this.status = payload.getByte();
        
    }

    /**
    * Constructor for a new message, just initializes the msgid
    */
    public msg_heartbeat_icarous(){
        msgid = MAVLINK_MSG_ID_HEARTBEAT_ICAROUS;
    }

    /**
    * Constructor for a new message, initializes the message with the payload
    * from a mavlink packet
    *
    */
    public msg_heartbeat_icarous(MAVLinkPacket mavLinkPacket){
        this.sysid = mavLinkPacket.sysid;
        this.compid = mavLinkPacket.compid;
        this.msgid = MAVLINK_MSG_ID_HEARTBEAT_ICAROUS;
        unpack(mavLinkPacket.payload);        
    }

      
    /**
    * Returns a string with the MSG name and data
    */
    public String toString(){
        return "MAVLINK_MSG_ID_HEARTBEAT_ICAROUS -"+" status:"+status+"";
    }
}
        